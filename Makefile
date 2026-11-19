.PHONY: up down escenario-normal escenario-falla escenario-bateria
up:
	./scripts/up.sh
down:
	./scripts/down.sh
escenario-normal:
	./scripts/escenario.sh normal
escenario-falla:
	./scripts/escenario.sh falla
escenario-bateria:
	./scripts/escenario.sh bateria_baja
