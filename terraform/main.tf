# AENIMUS Docker deployment v0.1.0
provider "docker" { host = var.docker_host }

resource "docker_network" "aenimus" { name = "${var.release_name}-network" }
resource "docker_volume" "data" { name = "${var.release_name}-data" }
resource "docker_volume" "models" { name = "${var.release_name}-models" }
resource "docker_volume" "vectors" { name = "${var.release_name}-vectors" }

resource "docker_image" "studio" {
  name = var.studio_image
  build { context = "${path.module}/.." }
}
resource "docker_image" "ollama" {
  name         = var.ollama_image
  keep_locally = true
}
resource "docker_image" "qdrant" {
  name         = var.qdrant_image
  keep_locally = true
}

resource "docker_container" "ollama" {
  name    = "${var.release_name}-ollama"
  image   = docker_image.ollama.image_id
  restart = "unless-stopped"
  networks_advanced { name = docker_network.aenimus.name }
  volumes {
    volume_name    = docker_volume.models.name
    container_path = "/root/.ollama"
  }
  security_opts = ["no-new-privileges:true"]
}

resource "docker_container" "qdrant" {
  name    = "${var.release_name}-qdrant"
  image   = docker_image.qdrant.image_id
  restart = "unless-stopped"
  networks_advanced { name = docker_network.aenimus.name }
  volumes {
    volume_name    = docker_volume.vectors.name
    container_path = "/qdrant/storage"
  }
  security_opts = ["no-new-privileges:true"]
}

resource "docker_container" "studio" {
  name    = "${var.release_name}-studio"
  image   = docker_image.studio.image_id
  restart = "unless-stopped"
  networks_advanced { name = docker_network.aenimus.name }
  ports {
    internal = 8787
    external = var.studio_port
    ip       = "127.0.0.1"
  }
  volumes {
    volume_name    = docker_volume.data.name
    container_path = "/data"
  }
  volumes {
    host_path      = var.workspace_path
    container_path = "/workspace"
  }
  env = [
    "AENIMUS_HOST=0.0.0.0",
    "AENIMUS_DATA_DIR=/data",
    "AENIMUS_WORKSPACE=/workspace",
    "AENIMUS_OLLAMA_URL=http://${docker_container.ollama.name}:11434",
    "AENIMUS_QDRANT_URL=http://${docker_container.qdrant.name}:6333",
    "AENIMUS_REQUIRE_APPROVAL=true"
  ]
  security_opts = ["no-new-privileges:true"]
  capabilities { drop = ["ALL"] }
}

resource "docker_container" "discord" {
  count   = var.enable_discord ? 1 : 0
  name    = "${var.release_name}-discord"
  image   = docker_image.studio.image_id
  restart = "unless-stopped"
  command = ["python", "-m", "app.discord_bot"]
  networks_advanced { name = docker_network.aenimus.name }
  env = [
    "AENIMUS_API_URL=http://${docker_container.studio.name}:8787/api",
    "DISCORD_BOT_TOKEN=${var.discord_bot_token}",
    "AENIMUS_DISCORD_CHANNEL_ID=${var.discord_channel_id}",
    "AENIMUS_DISCORD_ALLOWED_USER_IDS=${var.discord_allowed_user_ids}"
  ]
  security_opts = ["no-new-privileges:true"]
  capabilities { drop = ["ALL"] }
}
