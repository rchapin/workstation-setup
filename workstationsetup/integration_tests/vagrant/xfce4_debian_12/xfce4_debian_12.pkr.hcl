variable "version" {
  type    = string
  default = ""
}

locals { timestamp = regex_replace(timestamp(), "[- TZ:]", "") }

source "vagrant" "xfce4_debian_12" {
  add_force    = true
  communicator = "ssh"
  provider     = "virtualbox"
  source_path  = "debian/bookworm64"
  // box_version  = "12.20231009.1"
}

build {
  sources = ["source.vagrant.xfce4_debian_12"]

  provisioner "file" {
    source      = "id_rsa.pub"
    destination = "/var/tmp/id_rsa.pub"
  }
  provisioner "shell" {
    execute_command = "echo 'vagrant' | {{.Vars}} sudo -S -E bash '{{.Path}}'"
    script          = "provision.sh"
  }
}
