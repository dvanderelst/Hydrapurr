# components package for the Simplified build.
#
# Unlike BoardCode's version, this does not import every component up front:
# the Simplified build only carries the logging/time/SD/RTC modules, imported
# directly as `from components import MySystemLog` or
# `from components.MyStore import MyStore`.
