from stashapi.log import StashLogLevel
from body_tags import *

# Log level will skip logging lower levels
log_level = StashLogLevel.INFO

# Comment out tags you dont want in Stash
TAGS_TO_USE = (
    BodyShape,
    BodyType,
    BreastSize,
    ButtSize,
    BreastCup,
    HeightType,
    HipSize,
    BodyMassIndex
)