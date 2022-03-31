# Stdlib imports
from dateutil import parser
import datetime
import ftplib
import logging

# Core Django imports

# Third-party imports

# App imports

# Local imports

logger = logging.getLogger('django')

TLS_TYPES = ["ftps", "ftpes"]
MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def connection_timeout_decorator(func):
    """
    Decorator for reconnect after timeout and retry a function
    """
    def wrapper(self, *args):
        try:
            return func(self, *args)
        except Exception as e:
            try:
                logger.debug(f"Reconnection on func - {func} with exception - {e}")
                self.ftp = self._get_ftp()
                self._login()
                return func(self, *args)
            except Exception as totally_e:
                logger.debug(f"Totally failed in func - {func}, with exception - {totally_e}\n Arguments - {args}")
    return wrapper


class FTPHelper:
    """
    Should use like
    with FTPHelper(path, username, password) as ftp:
        ftp......
    Because it will close automatically after using
    """
    def __init__(self, path, username, password):
        self.type = path.split("://")[0]
        self.path = path.split("://")[1]
        self.credentials = {
            "username": username,
            "password": password
        }
        self.ftp = self._get_ftp()
        self._login()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _get_ftp(self):
        """
        Initialize ftp object
        """
        if self.type in TLS_TYPES:
            return ftplib.FTP_TLS(self.path)
        return ftplib.FTP(self.path)

    def _login(self):
        """
        Login with credentials
        """
        self.ftp.login(self.credentials["username"], self.credentials["password"])
        if self.type in TLS_TYPES:
            self.ftp.prot_p()

    def close(self):
        """
        Close connection
        """
        try:
            self.ftp.quit()
        except:
            pass

    @connection_timeout_decorator
    def get_folder_content(self, path):
        """
        Get all files anf folders in folder
        """
        res = self.ftp.nlst(path)
        return res

    @connection_timeout_decorator
    def get_file_bytes(self, path, name):
        """
        Get bytes from file in {path} with {name}
        """
        res = []
        self.ftp.retrbinary(f"RETR {path}/{name}", res.append)
        return res

    @connection_timeout_decorator
    def get_files(self, excludes, path) -> dict:
        """
        Get all files in folder (path) except (excludes)
        """
        pass

    @connection_timeout_decorator
    def _parse_date_for_folder(self, input_arr: list) -> datetime.date:
        """
        When we get data from LIST command we should parse date
        It is happened here
        """
        if ":" in input_arr[-1]:
            month = MONTHS[input_arr[1]]
            day = int(input_arr[2])
            year = datetime.datetime.now().year
        else:
            month = MONTHS[input_arr[0]]
            day = int(input_arr[1])
            year = int(input_arr[-1])
        return datetime.date(year=year, month=month, day=day)

    @connection_timeout_decorator
    def _parse_date_for_file(self, input_str: str) -> datetime.datetime:
        """
        parse string date to datetime
        """
        return parser.parse(input_str[4:].strip())

    @connection_timeout_decorator
    def get_dates_for_folders(self, path: str) -> dict:
        """
        Get dates for folders in (path)
        """
        res = {}
        arr = []
        self.ftp.retrlines(f"LIST {path}", arr.append)
        for line in arr:
            params = line.split(" ")
            res[f"{path}/{params[-1]}"] = self._parse_date_for_folder(params[-5:-1])
        return res

    @connection_timeout_decorator
    def get_dates_for_files(self, path: str) -> dict:
        """
        Get datetime for files in folder
        """
        res = {}
        arr = self.ftp.nlst(path)
        for file in arr:
            if file.split(".")[-1] in ["csv", "txt", "xlsx"]:
                try:
                    res[file] = self.get_file_date(file)
                except Exception as e:
                    logger.debug(f"File - {file} Exception in get file_date - {e}")
        return res

    @connection_timeout_decorator
    def get_file_date(self, path: str) -> datetime.datetime:
        raw_data = self.ftp.voidcmd(f"MDTM {path}")
        result = self._parse_date_for_file(raw_data)
        return result

    # def get_file_structure(self, path, level=1):
    #     print(f"{'  '*level}{path}")
    #     folders = self.get_folder_content(path)
    #     for folder in folders:
    #         if len(folder.split(".")) == 1:
    #             self.get_file_structure(folder, level+1)
    #         else:
    #             print(f"{'  ' * level}  {folder}")


