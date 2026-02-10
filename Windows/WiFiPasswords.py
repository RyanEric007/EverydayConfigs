import subprocess
import re

def get_saved_wifi_passwords():
    output = subprocess.check_output('netsh wlan show profiles', shell=True).decode()
    profiles = re.findall(r"All User Profile\s*:\s(.*)", output)

    for profile in profiles:
        profile = profile.strip()
        result = subprocess.check_output(
            f'netsh wlan show profile name="{profile}" key=clear', shell=True
        ).decode()
        password = re.search(r"Key Content\s*:\s(.*)", result)
        if password:
            print(f"{profile}: {password.group(1)}")

get_saved_wifi_passwords()