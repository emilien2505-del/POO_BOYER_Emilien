from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from cave_sgbd_sqlite import DB, Utilisateur, Cave, Etagere, ReferenceBouteille, Bouteille, Note, Archive, CapacityError

# --- Initialisation Flask + Base ---
app = Flask(__name__)
app.secret_key = "dev"     # clé pour signer la session (cookie) -> en prod : valeur secrète et forte
db = DB(); conn = db.conn  # connexion SQLite (fichier "cave.db"), créée dans DB._create()

# --- Décorateur pour protéger les pages privées ---
def login_required(view):
    """Si l'utilisateur n'est pas connecté, on le redirige vers /login.
       Usage: mettre @login_required au-dessus d'une route."""
    @wraps(view)
    def wrap(*a, **k):
        if not g.current_user:
            flash("Veuillez vous connecter.")
            return redirect(url_for("login", next=request.path))
        return view(*a, **k)
    return wrap

# --- Hook exécuté avant chaque requête HTTP ---
@app.before_request
def load_user():
    """Charge l'utilisateur courant depuis la session dans g.current_user.
       g est un conteneur 'global' valable pour la requête en cours."""
    uid = session.get("user_id")
    g.current_user = Utilisateur.find_by_id(conn, uid) if uid else None

# --- Variables injectées automatiquement dans tous les templates ---
@app.context_processor
def inject_globals():
    """Permet d'utiliser 'current_user' dans n'importe quelle page Jinja2 (navbar, etc.)"""
    return dict(current_user=g.get("current_user"))

# --- Pages d'accueil / redirections simples ---
@app.route("/")
def home():
    """Redirige vers le tableau de bord (qui renvoie vers Mes Caves)."""
    return redirect(url_for("dashboard"))

@app.route("/dashboard")
@login_required
def dashboard():
    """Page d'atterrissage après login : on renvoie vers la liste des caves."""
    return redirect(url_for("lister_caves"))

# =========================
# Authentification
# =========================

@app.route("/register", methods=["GET","POST"])
def register():
    """Inscription : GET -> formulaire ; POST -> crée l'utilisateur et redirige vers /login."""
    if request.method=="POST":
        # Création utilisateur ; le hash du mot de passe est géré dans Utilisateur.sauvegarder()
        u = Utilisateur(request.form["nom"], request.form["prenom"], login=request.form["login"],
                        password=request.form["password"], conn=conn)
        u.sauvegarder()
        flash("Compte créé. Connectez-vous.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    """Connexion : vérifie identifiant + mot de passe (hash), met l'id en session et redirige."""
    if request.method=="POST":
        user = Utilisateur.authenticate(conn, request.form["login"], request.form["password"])
        if user:
            session["user_id"] = user["id"]  # Sauvegarde en session pour les prochaines requêtes
            flash("Connecté.")
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Identifiants invalides.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    """Déconnexion : on efface la session et on retourne sur /login."""
    session.clear()
    flash("Déconnecté.")
    return redirect(url_for("login"))

# =========================
# Caves
# =========================

@app.route("/caves")
@login_required
def lister_caves():
    """Affiche les caves appartenant à l'utilisateur connecté."""
    caves = Cave(None,"",conn=conn).obtenir(utilisateur_id=g.current_user["id"])
    return render_template("caves.html", caves=caves)

@app.route("/caves/ajouter", methods=["GET","POST"])
@login_required
def ajouter_cave():
    """Ajoute une cave pour l'utilisateur courant."""
    if request.method=="POST":
        Cave(g.current_user["id"], request.form["nom"], conn=conn).sauvegarder()
        flash("Cave ajoutée.")
        return redirect(url_for("lister_caves"))
    return render_template("ajouter_cave.html")

@app.route("/caves/<int:cave_id>")
@login_required
def cave_detail(cave_id):
    """Détail d'une cave : liste ses étagères + formulaire pour en créer."""
    cave = Cave.find_by_id(conn, cave_id)
    # Sécurité : un utilisateur ne peut voir que ses caves
    if not cave or cave["utilisateur_id"] != g.current_user["id"]:
        flash("Accès refusé.")
        return redirect(url_for("lister_caves"))
    etageres = Etagere(None,"",0,conn=conn).obtenir(cave_id=cave_id)
    return render_template("cave_detail.html", cave=cave, etageres=etageres)

@app.route("/caves/<int:cave_id>/etageres/ajouter", methods=["POST"])
@login_required
def cave_ajouter_etagere(cave_id):
    """Ajoute une étagère (nom + capacité) dans la cave si elle appartient au user."""
    cave = Cave.find_by_id(conn, cave_id)
    if not cave or cave["utilisateur_id"] != g.current_user["id"]:
        flash("Accès refusé.")
        return redirect(url_for("lister_caves"))
    Etagere(cave_id, request.form["nom"], int(request.form["capacite"]), conn=conn).sauvegarder()
    flash("Étagère ajoutée.")
    return redirect(url_for("cave_detail", cave_id=cave_id))

# =========================
# Étagères
# =========================

@app.route("/etageres/<int:etagere_id>")
@login_required
def etagere_detail(etagere_id):
    """Affiche le contenu d'une étagère (formulaire d'ajout + tableau triable)."""
    e = Etagere.find_by_id(conn, etagere_id)
    if not e:
        flash("Étagère introuvable.")
        return redirect(url_for("lister_caves"))
    cave = Cave.find_by_id(conn, e["cave_id"])
    # Sécurité : vérifier que l'étagère appartient à une cave du user
    if cave["utilisateur_id"] != g.current_user["id"]:
        flash("Accès refusé.")
        return redirect(url_for("lister_caves"))
    # Paramètres de tri passés en query string (?sort=...&dir=...)
    sort = request.args.get("sort","annee"); dir_ = request.args.get("dir","asc")
    b = Bouteille(None,None,conn=conn)
    bouteilles = b.obtenir(etagere_id=etagere_id, sort=sort, dir=dir_)
    return render_template("etagere_detail.html", cave=cave, etagere=e, bouteilles=bouteilles, sort=sort, dir=dir_)

@app.route("/etageres/<int:etagere_id>/bouteilles/ajouter", methods=["POST"])
@login_required
def etagere_ajouter_bouteille(etagere_id):
    """Ajoute un lot de bouteilles :
       - crée/retouve la référence (unique sur domaine/nom/type/année/région),
       - insère la bouteille (respect de la capacité),
       - redirige vers l'étagère."""
    e = Etagere.find_by_id(conn, etagere_id)
    if not e:
        flash("Étagère introuvable.")
        return redirect(url_for("lister_caves"))
    cave = Cave.find_by_id(conn, e["cave_id"])
    if cave["utilisateur_id"] != g.current_user["id"]:
        flash("Accès refusé.")
        return redirect(url_for("lister_caves"))
    try:
        etiquette = request.form.get("etiquette_url") or None  # URL facultative (aucune image par défaut)
        # 1) Création/obtention de la référence (contrainte UNIQUE dans la base)
        ref = ReferenceBouteille(request.form["domaine"], request.form["nom"], request.form["type"],
                                 int(request.form["annee"]), request.form["region"],
                                 etiquette_url=etiquette, conn=conn)
        ref.sauvegarder()
        # 2) Ajout de la bouteille (contrôle de capacité dans Bouteille.sauvegarder)
        b = Bouteille(ref.id, etagere_id, prix=float(request.form.get("prix") or 0),
                      commentaire=request.form.get("commentaire"),
                      note_personnelle=request.form.get("note_personnelle", type=int),
                      quantite=int(request.form.get("quantite") or 1), conn=conn)
        b.sauvegarder()
        flash("Bouteille ajoutée.")
    except CapacityError as ex:
        # Si dépassement de capacité -> message d'erreur
        flash(str(ex))
    return redirect(url_for("etagere_detail", etagere_id=etagere_id))

# =========================
# Bouteilles (détail, modifier, archiver, supprimer)
# =========================

@app.route("/bouteilles/<int:bouteille_id>")
@login_required
def detail_bouteille(bouteille_id):
    """Page détail d'un lot : permet de modifier le prix/quantité/note perso, ou de déplacer d'étagère."""
    row = Bouteille.find_by_id(conn, bouteille_id)
    if not row:
        flash("Bouteille introuvable.")
        return redirect(url_for("lister_caves"))
    cave = Cave.find_by_id(conn, row["cave_id"])
    if cave["utilisateur_id"] != g.current_user["id"]:
        flash("Accès refusé.")
        return redirect(url_for("lister_caves"))
    # Liste des étagères de la même cave pour permettre le déplacement
    etageres = Etagere(None,"",0,conn=conn).obtenir(cave_id=cave["id"])
    return render_template("bouteille_detail.html", b=row, etageres=etageres)

@app.route("/bouteilles/<int:bouteille_id>/modifier", methods=["POST"])
@login_required
def modifier_bouteille(bouteille_id):
    """Mise à jour d'un lot (prix, quantité, note perso, commentaire, déplacement).
       La méthode Bouteille.sauvegarder vérifie la capacité si on augmente ou si on change d'étagère."""
    row = Bouteille.find_by_id(conn, bouteille_id)
    if not row:
        flash("Bouteille introuvable.")
        return redirect(url_for("lister_caves"))
    cave = Cave.find_by_id(conn, row["cave_id"])
    if cave["utilisateur_id"] != g.current_user["id"]:
        flash("Accès refusé.")
        return redirect(url_for("lister_caves"))
    try:
        b = Bouteille(row["ref_id"], int(request.form["etagere_id"]),
                      prix=request.form.get("prix", type=float),
                      commentaire=request.form.get("commentaire"),
                      note_personnelle=request.form.get("note_personnelle", type=int),
                      quantite=request.form.get("quantite", type=int),
                      conn=conn, id=bouteille_id)
        b.sauvegarder()
        flash("Bouteille mise à jour.")
    except CapacityError as e:
        flash(str(e))
    return redirect(url_for("detail_bouteille", bouteille_id=bouteille_id))

@app.route("/bouteilles/<int:bouteille_id>/archiver", methods=["POST"])
@login_required
def archiver_bouteille(bouteille_id):
    """Archive UNE unité (historique + décrémentation).
       Si quantité == 1 -> supprime le lot ; sinon quantité -= 1."""
    row = Bouteille.find_by_id(conn, bouteille_id)
    if row:
        cave = Cave.find_by_id(conn, row["cave_id"])
        if cave["utilisateur_id"] != g.current_user["id"]:
            flash("Accès refusé.")
            return redirect(url_for("lister_caves"))
        # On reconstruit un objet Bouteille exploitable côté modèle
        b = Bouteille(row["ref_id"], row["etagere_id"], prix=row["prix"], commentaire=row["commentaire"],
                      note_personnelle=row["note_personnelle"], quantite=row["quantite"], conn=conn, id=bouteille_id)
        # Ajoute une ligne dans 'archive' + met à jour la quantité
        b.archiver_une(g.current_user["id"], note_personnelle=request.form.get("note_personnelle", type=int),
                       commentaire=request.form.get("commentaire"))
        flash("Bouteille archivée (une unité).")
    return redirect(url_for("etagere_detail", etagere_id=row["etagere_id"] if row else None))

@app.route("/bouteilles/<int:bouteille_id>/supprimer", methods=["POST"])
@login_required
def supprimer_bouteille(bouteille_id):
    """Supprime entièrement le lot (sans passer par l'archive)."""
    row = Bouteille.find_by_id(conn, bouteille_id)
    if row:
        cave = Cave.find_by_id(conn, row["cave_id"])
        if cave["utilisateur_id"] != g.current_user["id"]:
            flash("Accès refusé.")
            return redirect(url_for("lister_caves"))
    Bouteille.supprimer(conn, bouteille_id)
    flash("Bouteille supprimée (lot entier).")
    return redirect(url_for("etagere_detail", etagere_id=row["etagere_id"] if row else None))

# =========================
# Communauté (références & avis)
# =========================

@app.route("/communaute")
def communaute():
    """Liste toutes les références + leur moyenne des notes de la communauté."""
    cur = conn.cursor()
    cur.execute("""SELECT r.*, (SELECT AVG(note) FROM note WHERE ref_id=r.id) AS moyenne
                   FROM ref_bouteille r ORDER BY COALESCE(annee,0) DESC, r.id DESC""" )
    refs = cur.fetchall()
    return render_template("communaute.html", refs=refs)

@app.route("/references/<int:ref_id>")
def reference_detail(ref_id):
    """Détail d'une référence : infos + moyenne + liste des avis + formulaire pour noter."""
    ref = ReferenceBouteille.find_by_id(conn, ref_id)
    if not ref:
        flash("Référence introuvable.")
        return redirect(url_for("communaute"))
    # Objet pratique pour calculer la moyenne et récupérer les avis
    rb = ReferenceBouteille(ref["domaine"], ref["nom"], ref["type"], ref["annee"], ref["region"],
                            etiquette_url=ref["etiquette_url"], conn=conn, id=ref_id)
    moy = rb.moyenne_communaute()
    notes = ReferenceBouteille.notes_for(conn, ref_id)
    return render_template("reference_detail.html", ref=ref, moyenne=moy, notes=notes)

@app.route("/references/<int:ref_id>/noter", methods=["POST"])
@login_required
def noter_reference(ref_id):
    """Ajoute un avis de la communauté sur une référence (note + commentaire)."""
    Note(ref_id, g.current_user["id"], note=request.form.get("note", type=int),
         commentaire=request.form.get("commentaire"), conn=conn).enregistrer()
    flash("Note enregistrée.")
    return redirect(url_for("reference_detail", ref_id=ref_id))

# =========================
# Archives 
# =========================

@app.route("/archives")
@login_required
def lister_archives():
    """Affiche l'historique des bouteilles sorties par l'utilisateur."""
    return render_template("archives.html", archives=Archive.lister(conn, utilisateur_id=g.current_user["id"]))

# --- Lancement local ---
if __name__ == "__main__":
    app.run(debug=True)
