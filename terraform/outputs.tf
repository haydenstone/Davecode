# AENIMUS Terraform outputs v0.1.0
output "studio_url" { value = "http://127.0.0.1:${var.studio_port}" }
output "release_name" { value = var.release_name }
output "migration_note" { value = "Set docker_host to an SSH Docker endpoint to move this release; preserve the three named volumes." }

