import win32serviceutil
import win32service
import win32event
import os
import logging
from client import main
import threading
import configparser


class ZomboidForwardClient(win32serviceutil.ServiceFramework):
    _svc_name_ = "ZomboidForwardClient"
    _svc_display_name_ = "ZomboidForwardClient"
    _svc_description_ = "Lightweight UDP forwarding service that can be used for forwarding Project Zomboid game servers"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.work_dir = os.path.dirname(__file__)
        self.logger: logging.Logger = self._getLogger(self._svc_name_)
        self.stop_event = threading.Event()

    def _getLogger(self, name):
        logger = logging.getLogger(f'[{name}]')
        handler = logging.FileHandler(
            os.path.join(self.work_dir, f"{name}.log"))
        formatter = logging.Formatter(
            '%(asctime)s %(name)-12s %(levelname)-5s %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger

    def SvcDoRun(self):
        self.logger.info("service is run....")
        self.ReportServiceStatus(win32service.SERVICE_START_PENDING)
        os.chdir(self.work_dir)
        conf = configparser.ConfigParser()
        conf.read('forward.ini')
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        main(conf, self.logger, self.stop_event)

    def SvcStop(self):
        self.logger.info("service is stop....")
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.stop_event.set()
        self.ReportServiceStatus(win32service.SERVICE_STOPPED)


if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(ZomboidForwardClient)