
import os
from fabric import Connection

class OS(object):

    @staticmethod
    def setup_inotify(conn: Connection, max_user_watches=524288) -> None:
        inotify_file_name = "inotify_max_watches.conf"
        inotify_remote_file_path = os.path.join("/etc/sysctl.d/", inotify_file_name)
        conn.run(f'echo "fs.inotify.max_user_watches = {max_user_watches}" > {inotify_remote_file_path}')
        conn.run(f"chmod 644 {inotify_remote_file_path}")
        conn.run("sysctl -p --system")