MAIN = main
ENGINE = xelatex
LATEXMK = latexmk -$(ENGINE) -interaction=nonstopmode

# Maximum chapter to include (default: 52)
# Usage: make CH=17  (only compile ch1-ch17)
CH ?= 52

CHAPTERS = $(wildcard ch*.tex)

.PHONY: all clean distclean view

all:
	@if [ $(CH) -lt 52 ]; then \
		echo "==> Building partial PDF (ch1-ch$(CH))"; \
		awk -v ch=$(CH) '/^\\input\{ch[0-9]+\.tex\}/ { match($$0, /[0-9]+/); if (substr($$0, RSTART, RLENGTH)+0 > ch) $$0 = "% " $$0 } { print }' $(MAIN).tex > main_build.tex; \
		$(LATEXMK) main_build.tex; \
		mv -f main_build.pdf $(MAIN).pdf; \
		rm -f main_build.*; \
	else \
		$(LATEXMK) $(MAIN).tex; \
	fi

clean:
	latexmk -c
	rm -f main_build.*

distclean:
	latexmk -C
	rm -f main_build.*

view: all
	open $(MAIN).pdf
