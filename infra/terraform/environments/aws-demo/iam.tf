# CP05: model read from AWS; environment import is gated in CP06.

resource "aws_iam_role_policy" "node_artifacts" {
  name = "lynk-release-artifacts"
  policy = jsonencode({
    Statement = [{
      Action   = "s3:GetObject"
      Effect   = "Allow"
      Resource = "${aws_s3_bucket.artifacts.arn}/releases/*"
      }, {
      Action   = "s3:PutObject"
      Effect   = "Allow"
      Resource = "${aws_s3_bucket.artifacts.arn}/deploy-logs/*"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.node.name
}

resource "aws_iam_openid_connect_provider" "github" {
  client_id_list  = ["sts.amazonaws.com"]
  tags            = {}
  thumbprint_list = ["ab9d0263244dd0326eb67015705a667e79cfe998"]
  url             = "https://token.actions.githubusercontent.com"
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role_policy_attachment" "node_ssm" {
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
  role       = aws_iam_role.node.name
}

resource "aws_iam_role_policy" "bootstrap" {
  name = "bootstrap-ssm"
  policy = jsonencode({
    Statement = [{
      Action   = "ssm:StartSession"
      Effect   = "Allow"
      Resource = ["arn:aws:ec2:ap-southeast-1:231136241975:instance/${aws_instance.node.id}", "arn:aws:ssm:ap-southeast-1::document/SSM-SessionManagerRunShell", "arn:aws:ssm:ap-southeast-1:231136241975:document/SSM-SessionManagerRunShell"]
      }, {
      Action   = ["ssm:TerminateSession", "ssm:ResumeSession"]
      Effect   = "Allow"
      Resource = "arn:aws:ssm:ap-southeast-1:231136241975:session/*"
      }, {
      Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
      Effect   = "Allow"
      Resource = "${aws_s3_bucket.artifacts.arn}/${aws_instance.node.id}/*"
      }, {
      Action   = ["s3:GetBucketLocation", "s3:ListBucket"]
      Effect   = "Allow"
      Resource = "${aws_s3_bucket.artifacts.arn}"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.bootstrap.name
}

resource "aws_iam_role_policy" "deploy" {
  name = "release-deploy"
  policy = jsonencode({
    Statement = [{
      Action   = ["s3:GetObject", "s3:PutObject"]
      Effect   = "Allow"
      Resource = "${aws_s3_bucket.artifacts.arn}/releases/*"
      }, {
      Action   = "ssm:SendCommand"
      Effect   = "Allow"
      Resource = ["arn:aws:ec2:ap-southeast-1:231136241975:instance/${aws_instance.node.id}", "arn:aws:ssm:ap-southeast-1:231136241975:document/LynkDeploy"]
      }, {
      Action   = ["ssm:GetCommandInvocation"]
      Effect   = "Allow"
      Resource = "*"
    }]
    Version = "2012-10-17"
  })
  role = aws_iam_role.deploy.name
}

resource "aws_iam_role" "status" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:ngqkhai@92835482/lynk-url-shortener@1365808803:environment:aws-demo"
        }
      }
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
    }]
    Version = "2012-10-17"
  })
  max_session_duration = 3600
  name                 = "lynk-github-argocd-status"
  path                 = "/"
}

resource "aws_iam_role_policy" "status" {
  name = "argocd-release-status-only"
  role = aws_iam_role.status.name
  policy = jsonencode({
    Statement = [{
      Action   = "ssm:SendCommand"
      Effect   = "Allow"
      Resource = ["arn:aws:ec2:ap-southeast-1:231136241975:instance/${aws_instance.node.id}", "arn:aws:ssm:ap-southeast-1:231136241975:document/${aws_ssm_document.argocd_status.name}"]
      }, {
      Action   = "ssm:GetCommandInvocation"
      Effect   = "Allow"
      Resource = "*"
    }]
    Version = "2012-10-17"
  })
}

resource "aws_iam_instance_profile" "node" {
  name = "lynk-k3s-dev-InstanceProfile-laelrId0FDdg"
  path = "/"
  role = aws_iam_role.node.name
  tags = {}
}

resource "aws_iam_role" "bootstrap" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:ngqkhai@92835482/lynk-url-shortener@1365808803:environment:aws-bootstrap"
        }
      }
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
    }]
    Version = "2012-10-17"
  })
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "lynk-github-bootstrap"
  path                  = "/"
  tags                  = {}
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "deploy" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:ngqkhai@92835482/lynk-url-shortener@1365808803:environment:aws-demo"
        }
      }
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github.arn
      }
    }]
    Version = "2012-10-17"
  })
  force_detach_policies = false
  max_session_duration  = 7200
  name                  = "lynk-github-deploy"
  path                  = "/"
  tags                  = {}
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_iam_role" "node" {
  assume_role_policy = jsonencode({
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
    Version = "2012-10-17"
  })
  force_detach_policies = false
  max_session_duration  = 3600
  name                  = "lynk-k3s-dev-InstanceRole-kGsx9JYHkqVh"
  path                  = "/"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  lifecycle {
    prevent_destroy = true
  }
}
