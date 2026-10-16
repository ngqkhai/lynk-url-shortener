# CP05: model read from AWS; environment import is gated in CP06.

resource "aws_s3_bucket_public_access_block" "artifacts" {
  block_public_acls       = true
  block_public_policy     = true
  bucket                  = aws_s3_bucket.artifacts.id
  ignore_public_acls      = true
  region                  = "ap-southeast-1"
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  region = "ap-southeast-1"
  rule {
    blocked_encryption_types = ["SSE-C"]
    bucket_key_enabled       = false
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket" "artifacts" {
  bucket              = "lynk-k3s-dev-artifactbucket-acumvnfx55sd"
  bucket_namespace    = "global"
  force_destroy       = false
  object_lock_enabled = false
  region              = "ap-southeast-1"
  tags = {
    Environment = "dev"
    Project     = "lynk"
  }
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  region = "ap-southeast-1"
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket                                 = aws_s3_bucket.artifacts.id
  region                                 = "ap-southeast-1"
  transition_default_minimum_object_size = "all_storage_classes_128K"
  rule {
    id     = "ExpireDeploymentArtifacts"
    status = "Enabled"
    expiration {
      date = null
      days = 7
    }
    filter {
      prefix = "artifacts/"
    }
  }
  rule {
    id     = "ExpireDeploymentLogs"
    status = "Enabled"
    expiration {
      date = null
      days = 14
    }
    filter {
      prefix = "deploy-logs/"
    }
  }
}
