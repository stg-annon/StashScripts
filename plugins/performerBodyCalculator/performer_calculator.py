import re, sys

import config
from body_tags import *

try:
    from stashapi.log import StashLogger
except ModuleNotFoundError:
    print("You need to install stashapp-tools. (https://pypi.org/project/stashapp-tools/)", file=sys.stderr)
    print("If you have pip (normally installed with python), run this command in a terminal (cmd): 'pip install stashapp-tools'", file=sys.stderr)
    sys.exit()
log = StashLogger(config.log_level)

class DebugException(Exception):
    pass
class WarningException(Exception):
    pass
class ErrorException(Exception):
    pass

CM_TO_INCH = 2.54
PERFORMER_FRAGMENT = """
id
name 
measurements
weight
height_cm
ethnicity
gender
"""

class StashPerformer:

    def __init__(self, resp) -> None:

        self.__dict__.update(resp)

        self.cupsize        = None
        self.band           = None
        self.waist          = None
        self.hips           = None

        self.bust           = None
        self.bust_band_diff = None
        self.breast_volume  = None

        self.bmi = 0

        self.tags_list = []

        self.parse_measurements()
        self.calculate_bmi()
        self.set_bmi_tag()

        self.set_breast_size()
        self.set_breast_cup()

        self.set_hip_size()

        self.set_butt_size()

        self.set_height_type()

        self.match_body_shapes()
        self.set_type_descriptor()
         
    def parse_measurements(self):
        if self.weight:
            self.weight = float(self.weight)
        if self.height_cm:
            self.height_cm = float(self.height_cm)

        self.measurements = self.measurements.replace(" ", "")

        if self.measurements == "":
            log.debug(f"No measurements found for {str(self)}")
            return

        # Full Measurements | Band, Cup Size, Waist, Hips | Example: "32D-28-34"
        band_cup_waist_hips = re.match(r'^(?P<band>\d+)(?P<cupsize>[a-zA-Z]+)\-(?P<waist>\d+)\-(?P<hips>\d+)$', self.measurements)
        if band_cup_waist_hips:
            m = band_cup_waist_hips.groupdict()
        else:
            # Fashion Measurements | Bust, Waist, Hips | Example: "36-28-34"
            bust_waist_hips = re.match(r'^(?P<bust>\d+)\-(?P<waist>\d+)\-(?P<hips>\d+)$', self.measurements)
            if bust_waist_hips:
                m = bust_waist_hips.groupdict()
            else:
                # Bra Measurements | Band, Cup Size | Example: "32D" or "32D (81D)"
                band_cup = re.match(r'^(?P<band>\d+)(?P<cupsize>[a-zA-Z]+)(?: ?\(\d+[a-zA-Z]+\))?$', self.measurements)
                if band_cup:
                    m = band_cup.groupdict()
                else:
                    raise WarningException(f"could not parse measurements: '{self.measurements}'")

        if m.get("cupsize"):
            self.cupsize = m.get("cupsize", "").upper()
        if m.get("band"):
            self.band    = float(m.get("band", 0))
        if m.get("bust"):
            self.bust    = float(m.get("bust", 0))
        if m.get("waist"):
            self.waist   = float(m.get("waist",0))
        if m.get("hips"):
            self.hips    = float(m.get("hips", 0))

        # convert metric to imperial
        if self.band and self.band > 50 and self.waist and self.waist > 50 and self.hips and self.hips > 50:
            self.band  = self.band / CM_TO_INCH
            self.waist = self.waist / CM_TO_INCH
            self.hips  = self.hips / CM_TO_INCH
            log.debug(f"converted measurements from metric {self.measurements} -> {self.band}{self.cupsize}-{self.waist}-{self.hips}")
        elif self.bust and self.bust > 50 and self.waist and self.waist > 50 and self.hips and self.hips > 50:
            self.bust  = self.bust / CM_TO_INCH
            self.waist = self.waist / CM_TO_INCH
            self.hips  = self.hips / CM_TO_INCH
            log.debug(f"converted measurements from metric {self.measurements} -> {self.bust}-{self.waist}-{self.hips}")

        if self.band and self.cupsize:
            self.bust_band_diff = get_bust_band_difference(self.cupsize)
            self.bust = self.band + self.bust_band_diff
            self.breast_volume = (self.band / 2.0) + self.bust_band_diff
            log.debug(f"Bra size {int(self.band)}{self.cupsize} converted to {(self.band / 2.0)} + {self.bust_band_diff} = {self.breast_volume} volume points")

    def calculate_bmi(self):
        if not self.weight or not self.height_cm:
            return
        breast_weight = approximate_breast_weight(self.bust_band_diff)
        self.bmi = (self.weight-breast_weight) / (self.height_cm/100) ** 2

    def match_body_shapes(self):
        self.body_shapes = calculate_shape(self)
        for body_shape in self.body_shapes:
            self.tags_list.append(body_shape)
        if not self.body_shapes:
            p_id = f"{self.name} ({self.id})"
            if not self.bust or not self.waist or not self.hips:
                log.debug(f"{p_id:>30}: could not classify bodyshape, missing required measurements")
            else:
                log.warning(f"{p_id:>30}: could not classify bodyshape bust={self.bust:.0f} waist={self.waist:.0f} hips={self.hips:.0f}")

    def set_type_descriptor(self):
        descriptor = None
        if not self.bmi:
            return
        descriptor = BodyType.match_threshold(self.bmi)
        if descriptor == BodyType.FIT and HeightType.SHORT.within_threshold(self.height_cm):
            descriptor = BodyType.PETITE
        if descriptor == BodyType.AVERAGE and self.body_shapes and any(bs in self.body_shapes for bs in CURVY_SHAPES):
            descriptor = BodyType.CURVY
        if descriptor:
            self.tags_list.append(descriptor)

    def set_breast_size(self):
        if not self.breast_volume:
            return
        if breast_size := BreastSize.match_threshold(self.breast_volume):
            self.tags_list.append(breast_size)

    def set_breast_cup(self):
        if not self.cupsize:
            return
        if breast_cup := BreastCup.match_threshold(self.cupsize):
            self.tags_list.append(breast_cup)

    def set_hip_size(self):
        if hip_size := calculate_hip_size(self):
            self.tags_list.append(hip_size)

    def set_butt_size(self):
        if not self.hips:
            return
        if butt_size := ButtSize.match_threshold(self.hips):
            self.tags_list.append(butt_size)
    
    def set_height_type(self):
        # only tuned on female heights
        if not self.height_cm or self.gender != 'FEMALE':
            return
        if self.height_cm > 160 and self.height_cm < 180:
            height_type = HeightType.AVERAGE
        else:
            height_type = HeightType.match_threshold(self.height_cm)
        if height_type:
            self.tags_list.append(height_type)

    def set_bmi_tag(self):
        if bmi_tag := calculate_bmi(self):
            self.tags_list.append(bmi_tag)

    def get_tag_updates(self, tag_updates={}):
        for tag_enum in self.tags_list:
            tag_updates[tag_enum].append(self.id)

    def __str__(self) -> str:
        descriptor = "N/A"
        p_id = f"{self.name} ({self.id})"
        p_str = f"{p_id:>25}"
        if self.band and self.cupsize:
            p_str += f" {self.band:.0f}{self.cupsize}"
        elif self.bust:
            p_str += f" {self.bust:.0f}"
        if self.waist and self.hips:
            p_str += f"-{self.waist:.0f}-{self.hips:.0f}"
        p_str += f" {self.bmi:5.2f}bmi"
        return p_str
    def __repr__(self) -> str:
        return str(self)

