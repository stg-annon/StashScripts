import re, sys, json
from pathlib import Path

from stashapi.stashapp import StashInterface
import stashapi.log as log

plugin_path = Path(__file__).parent
probe_pattern = r'^time=".+?" level=error msg="error processing.+?: running ffprobe on .+?: (?P<probe>FFProbe encountered an error with <(?P<file>.+)>.+$)'
        
def main():
	global stash
	
	json_input = json.loads(sys.stdin.read())

	stash = StashInterface(json_input["server_connection"])

	MODE = json_input['args']['mode']
	
	if MODE == "file_check":
		check_log()
	if MODE == "scan_check":
		stash.metadata_scan()
		stash.run_plugin_task("findFileErrors", "file_check")

	log.exit("ok")

def check_log():
	log_path = stash.get_configuration("general { logFile }")["general"]["logFile"]
	
	file_errors = {}
	with open(log_path, mode="r") as log_file:
		for line in log_file:
			m = re.match(probe_pattern, line)
			if not m:
				continue
			file_errors[m.group(2)] = m.group(1)

	with open(Path(plugin_path,"files_with_errors.txt"), "w") as error_log:
		for file_path, probe_error in file_errors.items():
			file_path = Path(file_path)
			if not file_path.exists():
				continue # ignore files that no longer exist
			error_log.write(f"{file_path}\n")

if __name__ == '__main__':
	main()
	