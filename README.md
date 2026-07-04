# confease

Project goal and description.

## Installation

## Usage

```python
# Create config instance in your base file (confif.py, constants.py, utils.py, ...)
from argparse import ArgumentParser
from confease import Confease

args = ArgumentParser().parse_args()

CONF = Confease(f'~/.config/{__name__}/conf.yaml', APP_DIR='~/Apps', MORE='CONFIG', KEYS=3)
# now I can use configuration in all my files by simply importing this object
CONF.get('APP_DUR') # None
CONF.get('APP_DIR') # '~/Apps'
CONF.set('new_key', 1312)
CONF.get('new_key') # '1312'
CONF.get('new_key', cast=int) # 1312
CONF.get('new_key', cast=float) # 1312.0
CONF.get('new_key', cast=dict) # '1312' (print error and returns string value)

CONF.load_sources(args, '/path/to/file1', '/path/to/file2', '/path/to/file3')
# Update the configuration object from multiple sources, with import rules
CONF.get('OTHER_VALUE') # New sources may have set new values
CONF.save() # save current conf into self._path

```
## Documentation

## License
