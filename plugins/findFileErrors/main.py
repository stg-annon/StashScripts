import re, sys, json
from pathlib import Path
from string import Template

from stashapi.stashapp import StashInterface
import stashapi.log as log

plugin_path = Path(__file__).parent

txt_file_path = Path(plugin_path, "errors")
txt_file_path.mkdir(exist_ok=True)

TAG_TEMPLATE = Template("[FileError] $error_type generation error")
FILE_ENCODING = "utf-8"
        
def main():
	global stash
	
	json_input = json.loads(sys.stdin.read())

	stash = StashInterface(json_input["server_connection"])

	MODE = json_input['args']['mode']
	
	if MODE == "scan_errors":
		find_scan_errors()
	if MODE == "generate_errors":
		file_errors = find_generate_errors()
		tag_scenes_with_file_errors(file_errors)
	if MODE == "scan_check":
		stash.metadata_scan()
		stash.run_plugin_task("findFileErrors", "Find Scan Errors")
	# TODO
	# if MODE == "generate_check":
	# 	stash.metadata_generate()
	# 	stash.run_plugin_task("findFileErrors", "generate_errors")

	log.exit("ok")

def find_scan_errors():
	ffprobe_pattern = r'(?P<probe>FFProbe encountered an error with <(?P<file>.+)>)'
	log_path = stash.get_configuration("general { logFile }")["general"]["logFile"]
	
	file_errors = {}
	with open(log_path, mode="r", encoding=FILE_ENCODING) as log_file:
		for i, line in enumerate(log_file):
			try:
				if m := re.search(ffprobe_pattern, line):
					file_errors[m.group(2)] = m.groupdict()
			except Exception as e:
				log.debug(f"error reading line {i} of log file: {e}")

	errors_path = Path(txt_file_path,"scan_errors.txt")
	with open(errors_path, "w", encoding=FILE_ENCODING) as error_log:
		for file_path, match_dict in file_errors.items():
			file_path = Path(file_path)
			if not file_path.exists():
				continue # ignore files that no longer exist
			error_log.write(f"{file_path}\n")

	log.info(f"found {len(file_errors)} files with errors logged to {errors_path}")

def find_generate_errors():
	generate_pattern = r'error generating (?P<type>\w+?):.+?ffmpeg.+?<.+?-i (?P<file>.+) -frames'
	log_path = stash.get_configuration("general { logFile }")["general"]["logFile"]
	
	# find errors in log file
	file_errors = {}
	with open(log_path, mode="r", encoding=FILE_ENCODING) as log_file:
		for line in log_file:
			m = re.search(generate_pattern, line)
			if not m:
				continue
			file_errors[m.group(2)] = m.groupdict()

	errors_path = Path(txt_file_path,"generate_errors.txt")
	with open(errors_path, "w", encoding=FILE_ENCODING) as error_log:
		for file_path, match_dict in file_errors.items():
			file_path = Path(file_path)
			if not file_path.exists():
				continue # ignore files that no longer exist
			error_log.write(f"{file_path}\n")

	return file_errors

def tag_scenes_with_file_errors(file_errors):

	count = len(file_errors)
	log.info(f"found {count} file errors looking for related scenes...")

	tag_id_lookup = {}

	# find scene in stash with file
	scene_ids_with_errors = 0
	for i, error_tuple in enumerate(file_errors.items()):
		file_path, error_dict = error_tuple
		log.progress(i/count)
		file_path = Path(file_path)
		scenes = stash.find_scenes({
			"path": {
				"value": f"{file_path}\"",
				"modifier": "INCLUDES"
			}
		})
		if len(scenes) != 1:
			log.info(error_dict)
			continue
		scene_id = scenes[0]["id"]
		tag_name = TAG_TEMPLATE.substitute(error_type=error_dict.get("type","").lower())
		tag_id = tag_id_lookup.get(tag_name)
		if not tag_id:
			tag_id = stash.find_tag(tag_name, create=True).get("id")
			tag_id_lookup[tag_name] = tag_id	
		stash.update_scenes({
			"ids": [scene_id],
			"tag_ids": { "ids": [tag_id], "mode": "ADD"}
		})
		scene_ids_with_errors += 1

	log.info(f"found and tagged {scene_ids_with_errors} scenes that had files with errors")
		

if __name__ == '__main__':
	main()
	