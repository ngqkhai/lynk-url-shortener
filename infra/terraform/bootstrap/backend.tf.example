# Add as backend.tf AFTER the initial local-state apply creates and secures S3.
# Then init -migrate-state with ../backends/bootstrap.s3.tfbackend
# with the verified bucket name already configured.
terraform {
  backend "s3" {}
}
