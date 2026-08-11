import os
from pathlib import Path

from utils.env_loader import load_env_file

load_env_file(Path(__file__).resolve().parents[1] / ".env")

JENKINS_SERVICES = {
    "ARMS": {"token": os.environ.get("JENKINS_TOKEN_ARMS", ""), "job_name": "CCRS"},
    "Default Web Site": {"token": os.environ.get("JENKINS_TOKEN_ARMS", ""), "job_name": "SERVICE_IIS"},
    "GoWFM": {"token": os.environ.get("JENKINS_TOKEN_GOWFM", ""), "job_name": "SERVICE_IIS"},
    "ECMS_TOMCAT_APP": {"token": os.environ.get("JENKINS_TOKEN_ECMS_TOMCAT", ""), "job_name": "SERVICE_TOMCAT"}
}
