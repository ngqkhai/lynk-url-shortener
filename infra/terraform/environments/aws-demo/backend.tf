# Activate only after bootstrap migration and isolated backend checks pass.
terraform {
  backend "s3" {}
}
