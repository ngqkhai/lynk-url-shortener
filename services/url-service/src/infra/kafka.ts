import { Kafka, logLevel } from 'kafkajs';
import type { UrlCreated } from '@lynk/shared/events';
export interface EventPublisher {
  publish(events: UrlCreated[]): Promise<void>;
  close(): Promise<void>;
}
export function createEventPublisher(brokers: string[]): EventPublisher {
  const kafka = new Kafka({
    clientId: 'lynk-url-outbox',
    brokers,
    logLevel: logLevel.NOTHING,
    connectionTimeout: 1000,
    requestTimeout: 2000,
    retry: { retries: 2, initialRetryTime: 200, maxRetryTime: 2000 },
  });
  const producer = kafka.producer({ allowAutoTopicCreation: false, maxInFlightRequests: 1 });
  return {
    publish: async (events) => {
      await producer.connect();
      await producer.send({
        topic: 'url.created',
        acks: -1,
        timeout: 2000,
        messages: events.map((event) => ({
          key: event.data.shortCode,
          value: JSON.stringify(event),
        })),
      });
    },
    close: () => producer.disconnect(),
  };
}
