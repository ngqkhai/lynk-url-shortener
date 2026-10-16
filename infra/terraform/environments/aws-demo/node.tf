# CP05: model read from AWS; environment import is gated in CP06.

resource "aws_instance" "node" {
  ami                                  = "ami-09fad7bb72d4e6685"
  availability_zone                    = "ap-southeast-1a"
  disable_api_stop                     = false
  disable_api_termination              = false
  ebs_optimized                        = false
  force_destroy                        = false
  get_password_data                    = false
  hibernation                          = false
  iam_instance_profile                 = aws_iam_instance_profile.node.name
  instance_initiated_shutdown_behavior = "stop"
  instance_type                        = "t3.medium"
  monitoring                           = false
  placement_partition_number           = 0
  private_ip                           = "10.70.1.221"
  region                               = "ap-southeast-1"
  secondary_private_ips                = []
  source_dest_check                    = true
  subnet_id                            = aws_subnet.public.id
  tags = {
    Environment = "dev"
    Name        = "lynk-k3s-dev"
    Project     = "lynk"
  }
  tenancy                = "default"
  user_data              = file("${path.module}/user-data.sh")
  vpc_security_group_ids = [aws_security_group.node.id]
  capacity_reservation_specification {
    capacity_reservation_preference = "open"
  }
  cpu_options {
    core_count       = 1
    threads_per_core = 2
  }
  credit_specification {
    cpu_credits = "standard"
  }
  enclave_options {
    enabled = false
  }
  maintenance_options {
    auto_recovery = "default"
  }
  metadata_options {
    http_endpoint               = "enabled"
    http_protocol_ipv6          = "disabled"
    http_put_response_hop_limit = 1
    http_tokens                 = "required"
    instance_metadata_tags      = "disabled"
  }
  private_dns_name_options {
    enable_resource_name_dns_a_record    = false
    enable_resource_name_dns_aaaa_record = false
    hostname_type                        = "ip-name"
  }
  root_block_device {
    delete_on_termination = false
    encrypted             = true
    iops                  = 3000
    kms_key_id            = "arn:aws:kms:ap-southeast-1:231136241975:key/5958aeb7-b5ca-4d32-abc8-eeb294e14db6"
    tags                  = {}
    throughput            = 125
    volume_size           = 30
    volume_type           = "gp3"
  }
  depends_on = [aws_route.default, aws_iam_role_policy_attachment.node_ssm, aws_iam_role_policy.node_artifacts]
  lifecycle {
    prevent_destroy = true
  }
}
