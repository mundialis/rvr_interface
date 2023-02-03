MODULE_TOPDIR = ../../..

PGM = m.analyse.buildings

include $(MODULE_TOPDIR)/include/Make/Other.make
include $(MODULE_TOPDIR)/include/Make/Python.make

MODULES = analyse_buildings_lib __init__

ETCDIR = $(ETC)/$(PGM)

PYFILES := $(patsubst %,$(ETCDIR)/%.py,$(MODULES))

default: $(PYFILES)

$(ETCDIR):
	$(MKDIR) $@

$(ETCDIR)/%: % | $(ETCDIR)
	$(INSTALL_DATA) $< $@

install:
	cp -r $(ETCDIR) $(INST_DIR)/etc
