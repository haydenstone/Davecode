# AENIMUS Terraform constraints v0.1.0
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    docker = { source = "kreuzwerker/docker", version = "~> 3.6" }
    random = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

