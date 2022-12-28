variable "version" {
  type    = string
  default = ""
}

locals { timestamp = regex_replace(timestamp(), "[- TZ:]", "") }

source "vagrant" "xfce4_debian_11" {
  add_force    = true
  communicator = "ssh"
  provider     = "virtualbox"
  source_path  = "debian/bullseye64"
  // TODO: Figure out how to specify a version for this box.  The following does NOT work
  // version      = "11.20221219.1"
}

build {
  sources = ["source.vagrant.xfce4_debian_11"]

  provisioner "file" {
    source      = "id_rsa.pub"
    destination = "/var/tmp/id_rsa.pub"
  }
  provisioner "shell" {
    execute_command = "echo 'vagrant' | {{.Vars}} sudo -S -E bash '{{.Path}}'"
    script          = "provision.sh"
  }
}
