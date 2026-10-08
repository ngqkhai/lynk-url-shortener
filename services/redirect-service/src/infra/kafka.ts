import { Kafka, logLevel, type Consumer, type Producer } from 'kafkajs';
import type { DeadLetterSink, UrlCreatedHandler } from '../services/url-created.service.js';
import type { ServiceLogger } from '../services/redirect.service.js';

export interface EventConsumer {
  start(handler: UrlCreatedHandler): void;
  close(): Promise<void>;
}

export function createKafkaEvents(
  brokers: string[],
  logger: ServiceLogger,
): { consumer: EventConsumer; deadLetters: DeadLetterSink } {
  const kafka = new Kafka({
    clientId: 'lynk-redirect',
    brokers,
    logLevel: logLevel.NOTHING,
    connectionTimeout: 1000,
    // Group synchronization may legitimately wait during a rebalance.
    requestTimeout: 30000,
    retry: { retries: 2 },
  });
  const consumer: Consumer = kafka.consumer({
    groupId: 'lynk-redirect-v1',
    allowAutoTopicCreation: false,
    sessionTimeout: 30000,
    rebalanceTimeout: 30000,
    maxWaitTimeInMs: 1000,
    retry: { retries: 2, restartOnFailure: async () => false },
  });
  const producer: Producer = new Kafka({
    clientId: 'lynk-redirect-dlq',
    brokers,
    logLevel: logLevel.NOTHING,
    connectionTimeout: 1000,
    requestTimeout: 2000,
    retry: { retries: 2 },
  }).producer({ allowAutoTopicCreation: false });
  let running = false;
  let task: Promise<void> | undefined;
  let wakeRun: (() => void) | undefined;
  let wakeRetry: (() => void) | undefined;
  consumer.on(consumer.events.CRASH, ({ payload }) => {
    logger.warn(
      { error: payload.error, restart: payload.restart },
      'Kafka consumer crashed; reconnecting',
    );
    wakeRun?.();
  });
  consumer.on(consumer.events.GROUP_JOIN, ({ payload }) => {
    logger.info?.(
      {
        groupId: payload.groupId,
        durationMs: payload.duration,
        assignments: payload.memberAssignment,
      },
      'Kafka consumer joined group',
    );
  });
  const deadLetters: DeadLetterSink = {
    async send(raw, context) {
      await producer.send({
        topic: 'url.created.dlq',
        acks: -1,
        timeout: 2000,
        messages: [
          {
            key: `${context.partition}:${context.offset}`,
            value: JSON.stringify({
              sourceTopic: 'url.created',
              ...context,
              raw,
              reason: 'INVALID_EVENT',
            }),
          },
        ],
      });
    },
  };
  return {
    deadLetters,
    consumer: {
      start(handler) {
        if (running) return;
        running = true;
        task = (async () => {
          while (running) {
            try {
              await producer.connect();
              if (!running) break;
              await consumer.connect();
              if (!running) break;
              await consumer.subscribe({ topic: 'url.created', fromBeginning: true });
              const ended = new Promise<void>((resolve) => {
                wakeRun = resolve;
              });
              await consumer.run({
                autoCommit: false,
                eachBatchAutoResolve: false,
                eachBatch: async ({ batch, resolveOffset, heartbeat, isRunning, isStale }) => {
                  for (const message of batch.messages) {
                    if (!running || !isRunning() || isStale()) break;
                    // Retry persistence or DLQ failures without advancing this partition.
                    while (running && isRunning() && !isStale()) {
                      try {
                        await handler.handle(message.value?.toString() ?? null, {
                          partition: batch.partition,
                          offset: message.offset,
                        });
                        break;
                      } catch (error) {
                        logger.warn(
                          { error, partition: batch.partition, offset: message.offset },
                          'Event delivery failed; retrying',
                        );
                        await new Promise<void>((resolve) => {
                          const timer = setTimeout(resolve, 1000);
                          wakeRetry = () => {
                            clearTimeout(timer);
                            resolve();
                          };
                        });
                        await heartbeat();
                      }
                    }
                    if (!running || !isRunning() || isStale()) break;
                    resolveOffset(message.offset);
                    await consumer.commitOffsets([
                      {
                        topic: batch.topic,
                        partition: batch.partition,
                        offset: (BigInt(message.offset) + 1n).toString(),
                      },
                    ]);
                    await heartbeat();
                  }
                },
              });
              // One reconnect loop owns recovery; KafkaJS automatic restarts are disabled.
              if (running) await ended;
              if (running) {
                await consumer.disconnect();
                await producer.disconnect();
              }
            } catch (error) {
              logger.warn({ error }, 'Kafka consumer unavailable; reconnecting');
              await consumer.disconnect().catch(() => undefined);
              await producer.disconnect().catch(() => undefined);
              if (running)
                await new Promise<void>((resolve) => {
                  const timer = setTimeout(resolve, 1000);
                  wakeRetry = () => {
                    clearTimeout(timer);
                    resolve();
                  };
                });
            }
          }
        })();
      },
      async close() {
        running = false;
        wakeRun?.();
        wakeRetry?.();
        await consumer.stop();
        await task;
        await consumer.disconnect();
        await producer.disconnect();
      },
    },
  };
}
