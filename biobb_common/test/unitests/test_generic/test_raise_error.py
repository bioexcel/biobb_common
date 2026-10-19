# type: ignore
import subprocess
import pytest
from biobb_common.generic.biobb_object import BiobbObject
from biobb_common.tools.file_utils import launchlogger


class Block(BiobbObject):
    """
    | biobb_common Block
    | Minimal block to run a command.

    Args:
        properties (dict - Python dictionary object containing the tool parameters, not input/output files):

    Examples:
        Block(properties={})
    """

    @launchlogger
    def launch(self):
        self.stage_files()
        self.run_biobb()
        self.copy_to_host()
        self.remove_tmp_files()
        return self.return_code


def _run(cmd, **properties):
    obj = Block(properties={'disable_logs': True, **properties})
    obj.cmd = cmd
    obj.execute_command()
    return obj


def test_failure_without_raise_error():
    assert _run(['exit', '3']).return_code == 3


def test_failure_with_raise_error():
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        _run(['exit', '3'], raise_error=True)
    assert excinfo.value.returncode == 3


def test_success_with_raise_error():
    assert _run(['true'], raise_error=True).return_code == 0


def test_launchlogger_closes_logs_on_error(tmp_path):
    obj = Block(properties={'raise_error': True, 'can_write_console_log': False,
                            'path': str(tmp_path), 'sandbox_path': str(tmp_path)})
    obj.cmd = ['exit', '3']
    with pytest.raises(subprocess.CalledProcessError):
        obj.launch()
    assert not obj.out_log.handlers
    assert not obj.err_log.handlers
    assert 'exit code 3' in (tmp_path / 'log.out').read_text()
