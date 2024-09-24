# -*- coding: utf-8 -*-
"""Python wrapper for command line
"""
import os
import subprocess
from biobb_common.tools import file_utils as fu
import typing
from typing import Optional
import logging
from pathlib import Path


class CmdWrapper:
    """Command line wrapper using subprocess library
    """

    def __init__(self, cmd: typing.Iterable[str], shell_path: typing.Union[str, Path] = os.getenv('SHELL', '/bin/sh'), out_log: Optional[logging.Logger] = None, err_log: Optional[logging.Logger] = None,
                 global_log: Optional[logging.Logger] = None, env: Optional[typing.Mapping] = None, timeout: Optional[int] = None) -> None:

        self.cmd = cmd
        self.shell_path = shell_path
        self.out_log = out_log
        self.err_log = err_log
        self.global_log = global_log
        self.env = env
        self.timeout = timeout

    def log_output(self, exit_code: str, command: str, out: Optional[bytes] = None, err: Optional[bytes] = None, timeout: Optional[str] = None,
                   out_log: Optional[logging.Logger] = None, err_log: Optional[logging.Logger] = None, global_log: Optional[logging.Logger] = None) -> None:

        timeout_str = ''
        if timeout:
            timeout_str = f"Timeout: {timeout} seconds expired, killing process\n"
        command_str = f"Executing: {command[0:80]}..."
        exit_code_str = f"Exit code: {exit_code}"
        if out_log:
            out_log.info(command_str)
            out_log.info(exit_code_str)
            if timeout_str:
                out_log.info(timeout_str)
            if out:
                out_log.info(out.decode("utf-8"))
        else:
            print(command_str)
            print(exit_code_str)
            if timeout_str:
                print(timeout_str)
            print("")
        if err_log and err:
            err_log.info(err.decode("utf-8"))

        if global_log:
            global_log.info(f"{fu.get_logs_prefix()}{command_str}")
            global_log.info(f"{fu.get_logs_prefix()}{exit_code_str}")
            if timeout_str:
                global_log.info(f"{fu.get_logs_prefix()}{timeout_str}")

    def launch(self) -> int:
        cmd = " ".join(self.cmd)
        if self.out_log is None:
            print('')
            print("cmd_wrapper commnand print: " + cmd)
        else:
            self.out_log.info(cmd + '\n')

        new_env = {**os.environ.copy(), **self.env} if self.env else os.environ.copy()
        process = subprocess.Popen(cmd,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE,
                                   shell=True,
                                   executable=self.shell_path,
                                   env=new_env)
        try:
            out, err = process.communicate(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            out, err = process.communicate()
            process.returncode = 1
            self.log_output(exit_code=str(process.returncode), command=" ".join(self.cmd), out=out, err=err, timeout=str(self.timeout), out_log=self.out_log, err_log=self.err_log, global_log=self.global_log)
            return process.returncode

        process.wait()
        self.log_output(exit_code=str(process.returncode), command=" ".join(self.cmd), out=out, err=err, out_log=self.out_log, err_log=self.err_log, global_log=self.global_log)
        return process.returncode
