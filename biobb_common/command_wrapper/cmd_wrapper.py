# -*- coding: utf-8 -*-
"""Python wrapper for command line
"""
import os
import subprocess
from biobb_common.tools import file_utils as fu

class CmdWrapper():
    """Command line wrapper using subprocess library
    """

    def __init__(self, cmd, out_log=None, err_log=None, global_log=None, env=None):

        self.cmd = cmd
        self.out_log = out_log
        self.err_log = err_log
        self.global_log = global_log
        self.env = env

    def launch(self):
        cmd = " ".join(self.cmd)
        if self.out_log is None:
            print ('')
            print ("cmd_wrapper commnand print: " + cmd)

        new_env = self.env if self.env else os.environ.copy()

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=True,
                                   env=new_env)

        out, err = process.communicate()
        if self.out_log is None:
            print ("Exit, code {}".format(process.returncode))
        process.wait()

        # Write output to log
        if self.out_log is not None:
            self.out_log.info(cmd+'\n')
            self.out_log.info("Exit code {}".format(process.returncode)+'\n')
            if out:
                self.out_log.info(out.decode("utf-8"))

        if self.global_log is not None:
            self.global_log.info(fu.get_logs_prefix()+'Executing: '+cmd[0:80]+'...')
            self.global_log.info(fu.get_logs_prefix()+"Exit code {}".format(process.returncode))

        if self.err_log is not None:
            if err:
                self.err_log.info(err.decode("utf-8"))

        return process.returncode
