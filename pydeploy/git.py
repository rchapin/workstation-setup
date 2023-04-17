from fabric import Connection
from invoke import Context


class Git(object):
    @staticmethod
    def d():
        pass

    def configure_git(
        ctx: Context,
        conn: Connection,
        user: str,
        user_email: str,
        user_full_name: str,
        editor: str = "vim",
        default_pull_reconcile_method=None,
    ) -> None:
        conn.sudo(command=f'git config --global user.name "{user_full_name}"', user=user)
        conn.sudo(command=f'git config --global user.email "{user_email}"', user=user)
        conn.sudo(command=f'git config --global core.editor "{editor}"', user=user)
        if default_pull_reconcile_method:
            cmd_prefix = "git config --global"
            cmd = None
            if default_pull_reconcile_method == "rebase_false":
                cmd = f"{cmd_prefix} pull.rebase false"
            if default_pull_reconcile_method == "rebase_true":
                cmd = f"{cmd_prefix} pull.rebase true"
            if default_pull_reconcile_method == "ff_only":
                cmd = f"{cmd_prefix} pull.ff only"
            conn.sudo(command=cmd, user=user)
