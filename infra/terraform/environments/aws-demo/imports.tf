import {
  to = aws_vpc.network
  id = "vpc-09c4afddd4dfc6502"
}

import {
  to = aws_internet_gateway.public
  id = "igw-0bb523dabd532a6e9"
}

import {
  to = aws_subnet.public
  id = "subnet-00400b58035a53c92"
}

import {
  to = aws_route_table.public
  id = "rtb-0a44522bc2a4690b5"
}

import {
  to = aws_route_table_association.public
  id = "subnet-00400b58035a53c92/rtb-0a44522bc2a4690b5"
}

import {
  to = aws_security_group.node
  id = "sg-0548386ccc4cb294f"
}

import {
  to = aws_instance.node
  id = "i-03bb7dcb94ec8bd21"
}

import {
  to = aws_iam_role.node
  id = "lynk-k3s-dev-InstanceRole-kGsx9JYHkqVh"
}

import {
  to = aws_iam_instance_profile.node
  id = "lynk-k3s-dev-InstanceProfile-laelrId0FDdg"
}

import {
  to = aws_eip_association.node
  id = "eipassoc-0d9ab4bf56ed84463"
}

import {
  to = aws_route.default
  id = "rtb-0a44522bc2a4690b5_0.0.0.0/0"
}

import {
  to = aws_eip.node
  id = "eipalloc-0f88a7eca6c3660d1"
}

import {
  to = aws_s3_bucket.artifacts
  id = "lynk-k3s-dev-artifactbucket-acumvnfx55sd"
}

import {
  to = aws_s3_bucket_public_access_block.artifacts
  id = "lynk-k3s-dev-artifactbucket-acumvnfx55sd"
}

import {
  to = aws_s3_bucket_server_side_encryption_configuration.artifacts
  id = "lynk-k3s-dev-artifactbucket-acumvnfx55sd"
}

import {
  to = aws_s3_bucket_lifecycle_configuration.artifacts
  id = "lynk-k3s-dev-artifactbucket-acumvnfx55sd"
}

import {
  to = aws_s3_bucket_ownership_controls.artifacts
  id = "lynk-k3s-dev-artifactbucket-acumvnfx55sd"
}

import {
  to = aws_iam_role.deploy
  id = "lynk-github-deploy"
}

import {
  to = aws_iam_role.bootstrap
  id = "lynk-github-bootstrap"
}

import {
  to = aws_iam_openid_connect_provider.github
  id = "arn:aws:iam::231136241975:oidc-provider/token.actions.githubusercontent.com"
}

import {
  to = aws_ssm_document.deploy
  id = "LynkDeploy"
}

import {
  to = aws_iam_role_policy.node_artifacts
  id = "lynk-k3s-dev-InstanceRole-kGsx9JYHkqVh:lynk-release-artifacts"
}

import {
  to = aws_iam_role_policy.deploy
  id = "lynk-github-deploy:release-deploy"
}

import {
  to = aws_iam_role_policy.bootstrap
  id = "lynk-github-bootstrap:bootstrap-ssm"
}

import {
  to = aws_iam_role_policy_attachment.node_ssm
  id = "lynk-k3s-dev-InstanceRole-kGsx9JYHkqVh/arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
