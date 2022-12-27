FROM debian:11.6

ARG root_passwd
ARG user

# Ensure that we don't get any prompts when installing
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y \
    xfce4 \
    openssh-server \
    sudo \
    # Ensure that we can passwordlessly ssh to this host
    && sed -i '/PermitRootLogin/d' /etc/ssh/sshd_config \
    && echo "PermitRootLogin yes" >> /etc/ssh/sshd_config \
    # Generate keys for the ssh server
    && ssh-keygen -A \
    # Create a known password for the root user
    && echo "root:$root_passwd" | chpasswd \
    # Create an .ssh dir for the root user and set the permissions
    && mkdir /root/.ssh \
    && chown root: /root/.ssh \
    && chmod 700 /root/.ssh \
    # Create the run dir for sshd
    && mkdir -p /run/sshd


COPY bootstrap-debian_11.sh /var/tmp/
COPY install-python.sh /var/tmp/

RUN chmod +x /var/tmp/bootstrap-debian_11.sh \
    && /var/tmp/bootstrap-debian_11.sh -u $user \
    && chmod +x /var/tmp/install-python.sh

# Ensure to keep this as the last set of operations in the image so that we do not
# have to build all of the other layers prior.
COPY id_rsa.pub /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys

EXPOSE 22
CMD ["/usr/sbin/sshd","-D"]