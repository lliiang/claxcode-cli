"""SSH tools for remote server management using paramiko."""

from io import StringIO
from pathlib import Path
from typing import Any

import paramiko

from claxcode.tools.base import Tool
from claxcode.tools.registry import tool

# 危险命令列表
DANGEROUS_COMMANDS = [
    # 系统破坏性命令
    "rm -rf /",
    "rm -rf /*",
    "mkfs.",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # fork bomb
    "> /dev/sda",
    "mv / /dev/null",

    # 权限提升相关
    "chmod -R 777 /",
    "chmod 777 /",

    # 网络相关危险操作
    "iptables -F",
    "iptables --flush",
]


def is_dangerous_command(command: str) -> tuple[bool, str]:
    """检查命令是否包含危险操作.
    
    Args:
        command: 要检查的命令
        
    Returns:
        (是否危险, 原因)
    """
    command_lower = command.lower().strip()

    # 检查危险命令
    for dangerous in DANGEROUS_COMMANDS:
        if dangerous.lower() in command_lower:
            return True, f"命令包含危险操作: {dangerous}"

    # 检查删除根目录或系统目录
    dangerous_patterns = [
        (r'rm\s+-rf?\s+/\s', "删除根目录"),
        (r'rm\s+-rf?\s+/boot', "删除启动目录"),
        (r'rm\s+-rf?\s+/etc', "删除配置目录"),
        (r'rm\s+-rf?\s+/usr', "删除系统目录"),
        (r'rm\s+-rf?\s+/bin', "删除二进制目录"),
        (r'rm\s+-rf?\s+/sbin', "删除系统二进制目录"),
        (r'rm\s+-rf?\s+/lib', "删除库目录"),
        (r'rm\s+-rf?\s+/lib64', "删除库目录"),
    ]

    import re
    for pattern, reason in dangerous_patterns:
        if re.search(pattern, command_lower):
            return True, f"命令包含危险操作: {reason}"

    return False, ""


class SSHConnectionManager:
    """管理 SSH 连接的单例类."""

    _instance = None
    _connections: dict[str, paramiko.SSHClient] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_connection(self, host: str, port: int, username: str) -> paramiko.SSHClient | None:
        """获取已存在的连接."""
        key = f"{username}@{host}:{port}"
        return self._connections.get(key)

    def set_connection(self, host: str, port: int, username: str, client: paramiko.SSHClient) -> None:
        """保存连接."""
        key = f"{username}@{host}:{port}"
        self._connections[key] = client

    def close_connection(self, host: str, port: int, username: str) -> None:
        """关闭并移除连接."""
        key = f"{username}@{host}:{port}"
        if key in self._connections:
            try:
                self._connections[key].close()
            except Exception:
                pass
            del self._connections[key]

    def close_all(self) -> None:
        """关闭所有连接."""
        for client in self._connections.values():
            try:
                client.close()
            except Exception:
                pass
        self._connections.clear()


# 全局连接管理器
_ssh_manager = SSHConnectionManager()


def _get_ssh_client(
    host: str,
    port: int,
    username: str,
    password: str | None = None,
    private_key: str | None = None,
    private_key_path: str | None = None,
) -> paramiko.SSHClient:
    """创建或获取 SSH 连接.

    Args:
        host: 主机地址
        port: SSH 端口
        username: 用户名
        password: 密码（可选）
        private_key: 私钥内容字符串（可选）
        private_key_path: 私钥文件路径（可选）

    Returns:
        SSHClient 实例
    """
    # 检查是否已有连接
    client = _ssh_manager.get_connection(host, port, username)
    if client is not None:
        try:
            # 测试连接是否仍然有效
            transport = client.get_transport()
            if transport is not None and transport.is_active():
                return client
        except Exception:
            pass
        # 连接已断开，移除
        _ssh_manager.close_connection(host, port, username)

    # 创建新连接
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # 准备私钥
    pkey = None
    if private_key:
        pkey = paramiko.RSAKey.from_private_key(StringIO(private_key))
    elif private_key_path:
        private_key_path = Path(private_key_path).expanduser()
        if private_key_path.exists():
            pkey = paramiko.RSAKey.from_private_key_file(str(private_key_path))

    # 连接
    if pkey:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            pkey=pkey,
            timeout=30,
        )
    elif password:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=30,
        )
    else:
        # 尝试使用 SSH agent
        client.connect(
            hostname=host,
            port=port,
            username=username,
            timeout=30,
        )

    _ssh_manager.set_connection(host, port, username, client)
    return client


@tool
class SSHConnect(Tool):
    """建立 SSH 连接到远程服务器."""

    name = "ssh_connect"
    description = "建立 SSH 连接到远程服务器，支持密码或密钥认证."
    input_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "远程主机地址"},
            "port": {"type": "integer", "default": 22, "description": "SSH 端口"},
            "username": {"type": "string", "description": "用户名"},
            "password": {"type": "string", "description": "密码（可选，与密钥二选一）"},
            "private_key": {"type": "string", "description": "私钥内容字符串（可选）"},
            "private_key_path": {"type": "string", "description": "私钥文件路径（可选，如 ~/.ssh/id_rsa）"},
        },
        "required": ["host", "username"],
    }
    category = "ssh"
    required_permissions = ["execute"]

    async def execute(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str | None = None,
        private_key: str | None = None,
        private_key_path: str | None = None,
        **kwargs: Any,
    ) -> str:
        try:
            client = _get_ssh_client(
                host=host,
                port=port,
                username=username,
                password=password,
                private_key=private_key,
                private_key_path=private_key_path,
            )

            # 测试连接
            stdin, stdout, stderr = client.exec_command("echo 'SSH connection successful'")
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()

            if error:
                return f"SSH 连接已建立，但测试命令返回错误: {error}"

            return f"✅ SSH 连接成功建立到 {username}@{host}:{port}\n测试输出: {output}"

        except paramiko.AuthenticationException:
            return "❌ 认证失败: 请检查用户名、密码或密钥"
        except paramiko.SSHException as e:
            return f"❌ SSH 错误: {e}"
        except Exception as e:
            return f"❌ 连接失败: {e}"


@tool
class SSHExecute(Tool):
    """在远程服务器上执行 Shell 命令."""

    name = "ssh_execute"
    description = "通过 SSH 在远程服务器上执行 Shell 命令."
    input_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "远程主机地址"},
            "port": {"type": "integer", "default": 22, "description": "SSH 端口"},
            "username": {"type": "string", "description": "用户名"},
            "password": {"type": "string", "description": "密码（可选，如果已连接可省略）"},
            "private_key_path": {"type": "string", "description": "私钥路径（可选）"},
            "command": {"type": "string", "description": "要执行的命令"},
            "cwd": {"type": "string", "default": "", "description": "工作目录（可选）"},
            "timeout": {"type": "integer", "default": 60, "description": "命令超时时间（秒）"},
        },
        "required": ["host", "username", "command"],
    }
    category = "ssh"
    required_permissions = ["execute"]

    async def execute(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str | None = None,
        private_key_path: str | None = None,
        command: str = "",
        cwd: str = "",
        timeout: int = 60,
        **kwargs: Any,
    ) -> str:
        try:
            # 检查危险命令
            is_dangerous, reason = is_dangerous_command(command)
            if is_dangerous:
                return f"❌ 命令被拒绝: {reason}\n如需执行此命令，请使用本地终端手动执行。"

            # 获取或创建连接
            client = _get_ssh_client(
                host=host,
                port=port,
                username=username,
                password=password,
                private_key_path=private_key_path,
            )

            # 构建命令
            full_command = command
            if cwd:
                full_command = f"cd {cwd} && {command}"

            # 执行命令
            stdin, stdout, stderr = client.exec_command(full_command, timeout=timeout)

            # 读取输出
            exit_code = stdout.channel.recv_exit_status()
            output = stdout.read().decode("utf-8", errors="replace")
            error = stderr.read().decode("utf-8", errors="replace")

            # 构建结果
            result = []
            if output:
                result.append(f"[stdout]\n{output}")
            if error:
                result.append(f"[stderr]\n{error}")
            result.append(f"[exit code: {exit_code}]")

            return "\n".join(result)

        except paramiko.AuthenticationException:
            return "❌ 认证失败: 请检查用户名、密码或密钥"
        except Exception as e:
            return f"❌ 执行失败: {e}"


@tool
class SSHUpload(Tool):
    """上传文件到远程服务器."""

    name = "ssh_upload"
    description = "通过 SFTP 上传本地文件到远程服务器."
    input_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "远程主机地址"},
            "port": {"type": "integer", "default": 22, "description": "SSH 端口"},
            "username": {"type": "string", "description": "用户名"},
            "password": {"type": "string", "description": "密码（可选）"},
            "private_key_path": {"type": "string", "description": "私钥路径（可选）"},
            "local_path": {"type": "string", "description": "本地文件路径"},
            "remote_path": {"type": "string", "description": "远程目标路径"},
        },
        "required": ["host", "username", "local_path", "remote_path"],
    }
    category = "ssh"
    required_permissions = ["execute"]

    async def execute(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str | None = None,
        private_key_path: str | None = None,
        local_path: str = "",
        remote_path: str = "",
        **kwargs: Any,
    ) -> str:
        try:
            local_file = Path(local_path).expanduser()
            if not local_file.exists():
                return f"❌ 本地文件不存在: {local_path}"

            # 获取或创建连接
            client = _get_ssh_client(
                host=host,
                port=port,
                username=username,
                password=password,
                private_key_path=private_key_path,
            )

            # 使用 SFTP 上传
            sftp = client.open_sftp()
            try:
                sftp.put(str(local_file), remote_path)
                return f"✅ 文件上传成功\n本地: {local_file}\n远程: {username}@{host}:{remote_path}"
            finally:
                sftp.close()

        except Exception as e:
            return f"❌ 上传失败: {e}"


@tool
class SSHDownload(Tool):
    """从远程服务器下载文件."""

    name = "ssh_download"
    description = "通过 SFTP 从远程服务器下载文件到本地."
    input_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "远程主机地址"},
            "port": {"type": "integer", "default": 22, "description": "SSH 端口"},
            "username": {"type": "string", "description": "用户名"},
            "password": {"type": "string", "description": "密码（可选）"},
            "private_key_path": {"type": "string", "description": "私钥路径（可选）"},
            "remote_path": {"type": "string", "description": "远程文件路径"},
            "local_path": {"type": "string", "description": "本地目标路径（可选，默认为当前目录）"},
        },
        "required": ["host", "username", "remote_path"],
    }
    category = "ssh"
    required_permissions = ["execute"]

    async def execute(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        password: str | None = None,
        private_key_path: str | None = None,
        remote_path: str = "",
        local_path: str = "",
        **kwargs: Any,
    ) -> str:
        try:
            # 确定本地路径
            if local_path:
                local_file = Path(local_path).expanduser()
            else:
                # 使用远程文件名
                local_file = Path(Path(remote_path).name)

            # 确保父目录存在
            local_file.parent.mkdir(parents=True, exist_ok=True)

            # 获取或创建连接
            client = _get_ssh_client(
                host=host,
                port=port,
                username=username,
                password=password,
                private_key_path=private_key_path,
            )

            # 使用 SFTP 下载
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, str(local_file))
                return f"✅ 文件下载成功\n远程: {username}@{host}:{remote_path}\n本地: {local_file.absolute()}"
            finally:
                sftp.close()

        except Exception as e:
            return f"❌ 下载失败: {e}"


@tool
class SSHDisconnect(Tool):
    """断开 SSH 连接."""

    name = "ssh_disconnect"
    description = "断开与远程服务器的 SSH 连接."
    input_schema = {
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "远程主机地址"},
            "port": {"type": "integer", "default": 22, "description": "SSH 端口"},
            "username": {"type": "string", "description": "用户名"},
        },
        "required": ["host", "username"],
    }
    category = "ssh"
    required_permissions = ["execute"]

    async def execute(
        self,
        host: str,
        port: int = 22,
        username: str = "",
        **kwargs: Any,
    ) -> str:
        try:
            _ssh_manager.close_connection(host, port, username)
            return f"✅ 已断开与 {username}@{host}:{port} 的连接"
        except Exception as e:
            return f"❌ 断开连接失败: {e}"
