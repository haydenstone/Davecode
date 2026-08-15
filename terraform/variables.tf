# AENIMUS Terraform inputs v0.1.0
variable "release_name" {
  type    = string
  default = "aenimus"
}
variable "docker_host" {
  type        = string
  default     = "unix:///var/run/docker.sock"
  description = "Use ssh://deploy@elysium-405 for a remote Docker host."
}
variable "studio_port" {
  type    = number
  default = 8787
}
variable "workspace_path" {
  type    = string
  default = "/opt/aenimus/workspace"
}
variable "studio_image" {
  type    = string
  default = "aenimus-studio:0.1.0"
}
variable "ollama_image" {
  type    = string
  default = "ollama/ollama:0.11.4"
}
variable "qdrant_image" {
  type    = string
  default = "qdrant/qdrant:v1.15.1"
}
variable "enable_discord" {
  type    = bool
  default = false
}
variable "discord_bot_token" {
  type      = string
  sensitive = true
  default   = ""
}
variable "discord_channel_id" {
  type    = string
  default = ""
}
variable "discord_allowed_user_ids" {
  type    = string
  default = ""
}
