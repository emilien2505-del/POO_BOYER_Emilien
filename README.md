# POO_BOYER_Emilien

CAVE A VIN - APPLICATION
Une application web permettant à chaque utilisateur de gérer sa cave à vin personnelle : création de caves, d’étagères, ajout de bouteilles, archivage des dégustations et consultation de la communauté.

----------------------------------------------------------------------------

cave-a-vin
├── app.py                    # Point d’entrée Flask
├── cave_sgbd_sqlite.py       # Modèles et gestion SQLite
├── static/
│   └── style.css             # Style global du site
├── templates/                # Pages HTML (Jinja2)
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── caves.html
│   ├── cave_detail.html
│   ├── etagere_detail.html
│   ├── bouteille_detail.html
│   ├── communaute.html
│   └── archives.html
└── README.md                 # Documentation

----------------------------------------------------------------------------

Lancer l'application :

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

set FLASK_APP=app.py
set FLASK_ENV=development
flask run

----------------------------------------------------------------------------

Emilien Boyer
Projet individuel ETRS711 – Gestion de cave à vin
Année 2025
