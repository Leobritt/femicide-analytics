variable "docker_host" {
  description = "Onde o Docker roda: socket local ou ssh://usuario@servidor para a VM."
  type        = string
  default     = "unix:///var/run/docker.sock"
}

variable "postgres_version" {
  description = "Tag da imagem oficial do PostgreSQL (a VM da equipe usa a 16)."
  type        = string
  default     = "16-alpine"
}

variable "container_name" {
  description = "Nome do container do banco."
  type        = string
  default     = "femicide-pg"
}

variable "db_name" {
  description = "Nome do banco criado no container."
  type        = string
  default     = "femicide"
}

variable "db_user" {
  description = "Usuário dono do banco."
  type        = string
  default     = "femicide"
}

variable "db_password" {
  description = "Senha do banco. Sem valor padrão: vem de TF_VAR_db_password ou de terraform.tfvars (fora do git)."
  type        = string
  sensitive   = true
}

variable "bind_address" {
  description = "Endereço em que a porta é publicada. 127.0.0.1 deixa o banco acessível só na própria máquina."
  type        = string
  default     = "127.0.0.1"
}

variable "host_port" {
  description = "Porta do host ligada à 5432 do container (5433 evita conflito com outro PostgreSQL)."
  type        = number
  default     = 5433
}
