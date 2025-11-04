import sqlite3
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash

# Exception métier levée quand on dépasse la capacité d'une étagère
class CapacityError(Exception):
    pass


class DB:
    """Initialise la connexion SQLite et crée les tables au démarrage."""

    def __init__(self, db_name="cave.db"):
        # check_same_thread=False : autorise la même connexion depuis plusieurs threads (pratique en dev)
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        # row_factory : permet d'accéder aux colonnes par leur nom (row["col"])
        self.conn.row_factory = sqlite3.Row
        self._create()

    def _create(self):
        """Crée les tables si elles n'existent pas (idempotent)."""
        c = self.conn.cursor()

        # Utilisateurs (mot de passe hashé)
        c.execute("""CREATE TABLE IF NOT EXISTS utilisateur(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT, prenom TEXT, login TEXT UNIQUE, password_hash TEXT)""")

        # Caves (appartiennent à un utilisateur)
        c.execute("""CREATE TABLE IF NOT EXISTS cave(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            utilisateur_id INTEGER NOT NULL, nom TEXT NOT NULL)""")

        # Étagères (appartiennent à une cave, capacité imposée)
        c.execute("""CREATE TABLE IF NOT EXISTS etagere(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cave_id INTEGER NOT NULL, nom TEXT NOT NULL, capacite INTEGER NOT NULL)""")

        # Références de bouteilles (UNIQUE sur 5 colonnes -> évite les doublons)
        c.execute("""CREATE TABLE IF NOT EXISTS ref_bouteille(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domaine TEXT NOT NULL, nom TEXT NOT NULL, type TEXT NOT NULL,
            annee INTEGER NOT NULL, region TEXT NOT NULL, etiquette_url TEXT,
            UNIQUE(domaine,nom,type,annee,region))""")

        # Bouteilles physiques (un lot sur une étagère)
        c.execute("""CREATE TABLE IF NOT EXISTS bouteille(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_id INTEGER NOT NULL, etagere_id INTEGER NOT NULL,
            prix REAL, commentaire TEXT, note_personnelle INTEGER, quantite INTEGER NOT NULL DEFAULT 1)""")

        # Notes "communauté" (avis des utilisateurs sur une référence)
        c.execute("""CREATE TABLE IF NOT EXISTS note(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_id INTEGER NOT NULL, utilisateur_id INTEGER NOT NULL,
            note INTEGER, commentaire TEXT)""")

        # Archives (historique des sorties)
        c.execute("""CREATE TABLE IF NOT EXISTS archive(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ref_id INTEGER NOT NULL, utilisateur_id INTEGER NOT NULL,
            date_sortie TEXT NOT NULL, note_personnelle INTEGER, commentaire TEXT)""")

        self.conn.commit()


# -----------------------
# Modèle : Utilisateur
# -----------------------
class Utilisateur:
    """CRUD utilisateur + authentification (hash des mots de passe)."""

    def __init__(self, nom, prenom, login=None, password=None, conn=None, id=None):
        self.id = id
        self.nom = nom
        self.prenom = prenom
        self.login = login
        self._pwd = password   # Mot de passe en clair (temporaire) pour initialisation
        self.conn = conn

    def set_password(self, pwd):
        """Définit/Met à jour le mot de passe (stocké sous forme hashée)."""
        if not self.id:
            self.sauvegarder()
        ph = generate_password_hash(pwd)
        self.conn.execute("UPDATE utilisateur SET password_hash=? WHERE id=?", (ph, self.id))
        self.conn.commit()

    @staticmethod
    def authenticate(conn, login, password):
        """Vérifie login + mot de passe (comparaison sur le hash)."""
        cur = conn.cursor()
        cur.execute("SELECT * FROM utilisateur WHERE login=?", (login,))
        row = cur.fetchone()
        if row and row["password_hash"] and check_password_hash(row["password_hash"], password):
            return row
        return None

    def sauvegarder(self):
        """Insert/Update utilisateur. Si _pwd fourni : hash du mot de passe initial."""
        cur = self.conn.cursor()
        if self.id:
            cur.execute("UPDATE utilisateur SET nom=?, prenom=?, login=? WHERE id=?",
                        (self.nom, self.prenom, self.login, self.id))
        else:
            cur.execute("INSERT INTO utilisateur(nom, prenom, login) VALUES(?,?,?)",
                        (self.nom, self.prenom, self.login))
            self.id = cur.lastrowid
            if self._pwd:
                ph = generate_password_hash(self._pwd)
                cur.execute("UPDATE utilisateur SET password_hash=? WHERE id=?", (ph, self.id))
        self.conn.commit()

    @staticmethod
    def find_by_id(conn, id):
        """Retourne l'utilisateur par id (ou None)."""
        if not id:
            return None
        cur = conn.cursor()
        cur.execute("SELECT * FROM utilisateur WHERE id=?", (id,))
        return cur.fetchone()


# -------------
# Modèle : Cave
# -------------
class Cave:
    """CRUD sur les caves (reliées à un utilisateur)."""

    def __init__(self, utilisateur_id, nom, conn=None, id=None):
        self.id = id
        self.utilisateur_id = utilisateur_id
        self.nom = nom
        self.conn = conn

    def sauvegarder(self):
        """Insert/Update cave."""
        c = self.conn.cursor()
        if self.id:
            c.execute("UPDATE cave SET utilisateur_id=?, nom=? WHERE id=?",
                      (self.utilisateur_id, self.nom, self.id))
        else:
            c.execute("INSERT INTO cave(utilisateur_id,nom) VALUES(?,?)",
                      (self.utilisateur_id, self.nom))
            self.id = c.lastrowid
        self.conn.commit()

    def obtenir(self, utilisateur_id=None):
        """Liste les caves (option : filtrer par utilisateur)."""
        c = self.conn.cursor()
        if utilisateur_id:
            c.execute("SELECT * FROM cave WHERE utilisateur_id=? ORDER BY nom", (utilisateur_id,))
        else:
            c.execute("SELECT * FROM cave ORDER BY nom")
        return c.fetchall()

    @staticmethod
    def find_by_id(conn, id):
        """Détail d'une cave."""
        c = conn.cursor()
        c.execute("SELECT * FROM cave WHERE id=?", (id,))
        return c.fetchone()


# ----------------
# Modèle : Etagere
# ----------------
class Etagere:
    """Actions sur les étagères (chaque étagère appartient à une cave et a une capacité)."""

    def __init__(self, cave_id, nom, capacite, conn=None, id=None):
        self.id = id
        self.cave_id = cave_id
        self.nom = nom
        self.capacite = capacite
        self.conn = conn

    def sauvegarder(self):
        """Insert/Update étagère."""
        c = self.conn.cursor()
        if self.id:
            c.execute("UPDATE etagere SET cave_id=?, nom=?, capacite=? WHERE id=?",
                      (self.cave_id, self.nom, self.capacite, self.id))
        else:
            c.execute("INSERT INTO etagere(cave_id,nom,capacite) VALUES(?,?,?)",
                      (self.cave_id, self.nom, self.capacite))
            self.id = c.lastrowid
        self.conn.commit()

    def obtenir(self, cave_id=None, utilisateur_id=None):
        """Liste les étagères :
           - d'une cave donnée, ou
           - de toutes les caves d'un utilisateur (jointure)."""
        c = self.conn.cursor()
        if cave_id:
            c.execute("SELECT * FROM etagere WHERE cave_id=? ORDER BY nom", (cave_id,))
        elif utilisateur_id:
            c.execute("""SELECT e.* FROM etagere e
                         JOIN cave c ON c.id=e.cave_id
                         WHERE c.utilisateur_id=?
                         ORDER BY e.nom""", (utilisateur_id,))
        else:
            c.execute("SELECT * FROM etagere ORDER BY nom")
        return c.fetchall()

    @staticmethod
    def find_by_id(conn, id):
        """Détail d'une étagère."""
        c = conn.cursor()
        c.execute("SELECT * FROM etagere WHERE id=?", (id,))
        return c.fetchone()

    @staticmethod
    def capacite_restante(conn, etagere_id):
        """Capacité restante = capacité - somme des quantités présentes."""
        c = conn.cursor()
        c.execute("SELECT capacite FROM etagere WHERE id=?", (etagere_id,))
        row = c.fetchone()
        cap = row["capacite"] if row else 0
        c.execute("SELECT COALESCE(SUM(quantite),0) AS tot FROM bouteille WHERE etagere_id=?", (etagere_id,))
        occ = c.fetchone()["tot"]
        return cap - int(occ or 0)


# -------------------------
# Modèle : ReferenceBouteille
# -------------------------
class ReferenceBouteille:
    """Description unique d'un vin (mutualisée)."""

    def __init__(self, domaine, nom, type, annee, region, etiquette_url=None, conn=None, id=None):
        self.id = id
        self.domaine = domaine
        self.nom = nom
        self.type = type
        self.annee = annee
        self.region = region
        self.etiquette_url = etiquette_url
        self.conn = conn

    def sauvegarder(self):
        """Insère la référence si elle n'existe pas déjà (contrainte UNIQUE),
           puis récupère son id (utile pour créer la bouteille)."""
        c = self.conn.cursor()
        c.execute("""INSERT OR IGNORE INTO ref_bouteille(domaine,nom,type,annee,region,etiquette_url)
                     VALUES(?,?,?,?,?,?)""", (self.domaine, self.nom, self.type, self.annee, self.region, self.etiquette_url))
        c.execute("""SELECT id FROM ref_bouteille
                     WHERE domaine=? AND nom=? AND type=? AND annee=? AND region=?""",
                  (self.domaine, self.nom, self.type, self.annee, self.region))
        r = c.fetchone()
        if r:
            self.id = r["id"]
        self.conn.commit()

    @staticmethod
    def find_by_id(conn, rid):
        """Retourne une référence par id."""
        c = conn.cursor()
        c.execute("SELECT * FROM ref_bouteille WHERE id=?", (rid,))
        return c.fetchone()

    def moyenne_communaute(self):
        """Calcule la moyenne des notes de la communauté pour cette référence."""
        c = self.conn.cursor()
        c.execute("SELECT AVG(note) AS m FROM note WHERE ref_id=? AND note IS NOT NULL", (self.id,))
        r = c.fetchone()
        return float(r["m"]) if r and r["m"] is not None else None

    @staticmethod
    def notes_for(conn, ref_id):
        """Liste les avis (note + commentaire) avec nom/prénom des auteurs."""
        c = conn.cursor()
        c.execute("""SELECT n.*, u.nom, u.prenom
                     FROM note n JOIN utilisateur u ON u.id=n.utilisateur_id
                     WHERE ref_id=? ORDER BY n.id DESC""", (ref_id,))
        return c.fetchall()


# --------------
# Modèle : Bouteille
# --------------
class Bouteille:
    """Lot physique placé sur une étagère (quantité, prix, note perso, commentaire).
       Règle clé : NE PAS dépasser la capacité de l'étagère."""

    def __init__(self, ref_id, etagere_id, prix=None, commentaire=None, note_personnelle=None, quantite=1, conn=None, id=None):
        self.id = id
        self.ref_id = ref_id
        self.etagere_id = etagere_id
        self.prix = prix
        self.commentaire = commentaire
        self.note_personnelle = note_personnelle
        self.quantite = quantite
        self.conn = conn

    def _verifier_capacite(self, delta):
        """Vérifie qu'on peut ajouter 'delta' unités sur l'étagère courante."""
        restant = Etagere.capacite_restante(self.conn, self.etagere_id)
        if delta > restant:
            raise CapacityError(f"Capacité dépassée : reste {restant}, tentative +{delta}")

    def sauvegarder(self):
        """Insert ou Update d'un lot :
           - en INSERT : vérifie la capacité sur la quantité initiale
           - en UPDATE : gère l'augmentation de quantité et le déplacement d'étagère"""
        c = self.conn.cursor()
        if self.id:
            # Update : on récupère l'état précédent pour savoir quoi vérifier
            c.execute("SELECT quantite, etagere_id FROM bouteille WHERE id=?", (self.id,))
            row = c.fetchone()
            prev_q = row["quantite"] if row else 0
            prev_s = row["etagere_id"] if row else self.etagere_id
            delta = self.quantite - prev_q

            if prev_s != self.etagere_id:
                # Déplacement : on vérifie la capacité de la nouvelle étagère pour la quantité totale
                if self.quantite > Etagere.capacite_restante(self.conn, self.etagere_id):
                    raise CapacityError("Capacité dépassée sur la nouvelle étagère.")
            else:
                # Même étagère : si on augmente, on vérifie juste le delta
                if delta > 0:
                    self._verifier_capacite(delta)

            c.execute("""UPDATE bouteille SET etagere_id=?, prix=?, commentaire=?, note_personnelle=?, quantite=?
                      WHERE id=?""",
                      (self.etagere_id, self.prix, self.commentaire, self.note_personnelle, self.quantite, self.id))
        else:
            # Insert : la quantité initiale doit "rentrer"
            self._verifier_capacite(self.quantite)
            c.execute("""INSERT INTO bouteille(ref_id, etagere_id, prix, commentaire, note_personnelle, quantite)
                         VALUES(?,?,?,?,?,?)""",
                      (self.ref_id, self.etagere_id, self.prix, self.commentaire, self.note_personnelle, self.quantite))
            self.id = c.lastrowid
        self.conn.commit()

    def obtenir(self, utilisateur_id=None, etagere_id=None, sort="annee", dir="asc"):
        """Liste les bouteilles avec tri.
           - sort : colonne triable (whitelist pour éviter l'injection SQL)
           - dir  : 'asc' ou 'desc'
           - filtres : par utilisateur (toutes ses étagères) ou par étagère
        """
        whitelist = {"id","domaine","nom","type","annee","region","prix","quantite","note_personnelle"}
        sort_col = sort if sort in whitelist else "annee"
        direction = "DESC" if str(dir).lower()=="desc" else "ASC"
        c = self.conn.cursor()
        base = """
        SELECT b.id,b.quantite,b.prix,b.commentaire,b.note_personnelle,b.etagere_id,
               r.domaine,r.nom,r.type,r.annee,r.region,r.id AS ref_id,cave.utilisateur_id
        FROM bouteille b
        JOIN ref_bouteille r ON r.id=b.ref_id
        JOIN etagere e ON e.id=b.etagere_id
        JOIN cave ON cave.id=e.cave_id
        """
        cond=[]; params=[]
        if utilisateur_id:
            cond.append("cave.utilisateur_id=?"); params.append(utilisateur_id)
        if etagere_id:
            cond.append("b.etagere_id=?"); params.append(etagere_id)
        if cond:
            base += " WHERE " + " AND ".join(cond)
        base += f" ORDER BY {sort_col} {direction}, b.id ASC"
        c.execute(base, tuple(params))
        return c.fetchall()

    @staticmethod
    def find_by_id(conn, bid):
        """Retourne une bouteille avec les infos de sa référence + id de la cave (pour vérifier la propriété)."""
        c = conn.cursor()
        c.execute("""SELECT b.*, r.domaine, r.nom, r.type, r.annee, r.region, r.id AS ref_id, e.cave_id
                     FROM bouteille b
                     JOIN ref_bouteille r ON r.id=b.ref_id
                     JOIN etagere e ON e.id=b.etagere_id
                     WHERE b.id=?""", (bid,))
        return c.fetchone()

    def archiver_une(self, utilisateur_id, note_personnelle=None, commentaire=None):
        """Archive UNE unité :
           - insère une ligne dans 'archive' avec la date du jour
           - décrémente la quantité (ou supprime le lot si c'était la dernière)
        """
        c = self.conn.cursor()
        c.execute(
            "INSERT INTO archive(ref_id, utilisateur_id, date_sortie, note_personnelle, commentaire) "
            "VALUES(?,?,?,?,?)",
            (self.ref_id, utilisateur_id, date.today().isoformat(), note_personnelle, commentaire)
        )
        c.execute("SELECT quantite FROM bouteille WHERE id=?", (self.id,))
        q = c.fetchone()["quantite"]
        if q <= 1:
            c.execute("DELETE FROM bouteille WHERE id=?", (self.id,))
        else:
            c.execute("UPDATE bouteille SET quantite=quantite-1 WHERE id=?", (self.id,))
        self.conn.commit()

    @staticmethod
    def supprimer(conn, bid):
        """Supprime entièrement le lot (sans archivage)."""
        conn.execute("DELETE FROM bouteille WHERE id=?", (bid,))
        conn.commit()


# -----------
# Modèle : Note
# -----------
class Note:
    """Avis d'un utilisateur sur une RÉFÉRENCE (et non sur une bouteille/lot)."""

    def __init__(self, ref_id, utilisateur_id, note=None, commentaire=None, conn=None, id=None):
        self.id = id
        self.ref_id = ref_id
        self.utilisateur_id = utilisateur_id
        self.note = note
        self.commentaire = commentaire
        self.conn = conn

    def enregistrer(self):
        """Insère la note (0-20) + commentaire éventuel."""
        self.conn.execute("INSERT INTO note(ref_id,utilisateur_id,note,commentaire) VALUES(?,?,?,?)",
                          (self.ref_id, self.utilisateur_id, self.note, self.commentaire))
        self.conn.commit()


# ---------------
# Modèle : Archive
# ---------------
class Archive:
    """Lecture des archives (historiques de sortie), avec quelques jointures pour affichage lisible."""

    @staticmethod
    def lister(conn, utilisateur_id=None, ref_id=None):
        """Liste les archives :
           - filtrées par utilisateur (son historique), et/ou
           - filtrées par référence (historique d'un vin précis)
        """
        c = conn.cursor()
        base = """SELECT a.*, u.nom, u.prenom, r.domaine, r.nom AS rnom, r.type, r.annee, r.region
                  FROM archive a JOIN utilisateur u ON u.id=a.utilisateur_id
                  JOIN ref_bouteille r ON r.id=a.ref_id"""
        cond=[]; params=[]
        if utilisateur_id:
            cond.append("a.utilisateur_id=?"); params.append(utilisateur_id)
        if ref_id:
            cond.append("a.ref_id=?"); params.append(ref_id)
        if cond:
            base += " WHERE " + " AND ".join(cond)
        base += " ORDER BY a.id DESC"
        c.execute(base, tuple(params))
        return c.fetchall()
