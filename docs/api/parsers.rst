Parser API
==========

.. currentmodule:: confease

Parser classes implement a small static interface for loading and saving mapping data. :class:`Confease` uses these classes directly and can infer one from a path suffix when ``parser=None`` is passed.

Format Constants
----------------

.. data:: YAML

   ``.yaml`` suffix constant.

.. data:: YML

   ``.yml`` suffix constant.

.. data:: JSON

   ``.json`` suffix constant.

.. data:: TOML

   ``.toml`` suffix constant.

.. data:: INI

   ``.ini`` suffix constant.

.. data:: CFG

   ``.cfg`` suffix constant.

.. data:: CONF

   ``.conf`` suffix constant.

.. data:: CONFIG

   ``.config`` suffix constant.

.. data:: XML

   ``.xml`` suffix constant.

.. data:: CSV

   ``.csv`` suffix constant.

.. data:: PARSERS

   List of supported parser suffixes.

.. data:: PARSER_CLASSES

   Mapping from supported suffixes to parser classes.

Base Parser
-----------

.. autoclass:: Parser
   :members:
   :exclude-members: __weakref__

Concrete Parsers
----------------

.. autoclass:: Yaml
   :members:
   :exclude-members: __weakref__

.. autoclass:: Json
   :members:
   :exclude-members: __weakref__

.. autoclass:: Toml
   :members:
   :exclude-members: __weakref__

.. autoclass:: Ini
   :members:
   :exclude-members: __weakref__

.. autoclass:: Cfg
   :members:
   :exclude-members: __weakref__

.. autoclass:: Xml
   :members:
   :exclude-members: __weakref__

.. autoclass:: Csv
   :members:
   :exclude-members: __weakref__
