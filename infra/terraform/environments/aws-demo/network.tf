# CP05: model read from AWS; environment import is gated in CP06.

resource "aws_security_group" "node" {
  description = "Public HTTP/HTTPS only; administration through SSM"
  egress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 0
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "-1"
    security_groups  = []
    self             = false
    to_port          = 0
  }]
  ingress = [{
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 443
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 443
    }, {
    cidr_blocks      = ["0.0.0.0/0"]
    description      = ""
    from_port        = 80
    ipv6_cidr_blocks = []
    prefix_list_ids  = []
    protocol         = "tcp"
    security_groups  = []
    self             = false
    to_port          = 80
  }]
  name   = "lynk-k3s-dev-SecurityGroup-ECbsAlau3oZM"
  region = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  vpc_id = aws_vpc.network.id
}

resource "aws_route" "default" {
  destination_cidr_block      = "0.0.0.0/0"
  destination_ipv6_cidr_block = null
  gateway_id                  = aws_internet_gateway.public.id
  region                      = "ap-southeast-1"
  route_table_id              = aws_route_table.public.id
}

resource "aws_eip_association" "node" {
  allocation_id      = aws_eip.node.id
  instance_id        = aws_instance.node.id
  private_ip_address = "10.70.1.221"
  public_ip          = "3.1.88.80"
  region             = "ap-southeast-1"
}

resource "aws_eip" "node" {
  customer_owned_ipv4_pool = null
  domain                   = "vpc"
  network_border_group     = "ap-southeast-1"
  public_ipv4_pool         = "amazon"
  region                   = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_subnet" "public" {
  assign_ipv6_address_on_creation                = false
  availability_zone                              = "ap-southeast-1a"
  cidr_block                                     = "10.70.1.0/24"
  customer_owned_ipv4_pool                       = null
  enable_dns64                                   = false
  enable_resource_name_dns_a_record_on_launch    = false
  enable_resource_name_dns_aaaa_record_on_launch = false
  ipv4_ipam_pool_id                              = null
  ipv4_netmask_length                            = null
  ipv6_ipam_pool_id                              = null
  ipv6_native                                    = false
  ipv6_netmask_length                            = null
  map_public_ip_on_launch                        = false
  private_dns_hostname_type_on_launch            = "ip-name"
  region                                         = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  vpc_id = aws_vpc.network.id
}

resource "aws_vpc" "network" {
  assign_generated_ipv6_cidr_block     = false
  cidr_block                           = "10.70.0.0/16"
  enable_dns_hostnames                 = true
  enable_dns_support                   = true
  enable_network_address_usage_metrics = false
  instance_tenancy                     = "default"
  ipv4_ipam_pool_id                    = null
  ipv4_netmask_length                  = null
  ipv6_ipam_pool_id                    = null
  region                               = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_internet_gateway" "public" {
  region = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  vpc_id = aws_vpc.network.id
}

resource "aws_route_table" "public" {
  propagating_vgws = []
  region           = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  vpc_id = aws_vpc.network.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
