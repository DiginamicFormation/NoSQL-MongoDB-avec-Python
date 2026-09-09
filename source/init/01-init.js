// Joué UNE SEULE FOIS, au premier démarrage, quand /data/db est vide.
// Pour le rejouer : docker compose down -v && docker compose up -d

db.createUser({
  user: "app",
  pwd: "app-password",
  roles: [
    // dbOwner = readWrite + dbAdmin : nécessaire pour `collMod` (la validation
    // JSON Schema de provision.py, rejouée à chaque `app.py init`).
    { role: "dbOwner", db: "boutique" },
    // La suite de tests travaille sur une base jetable, qu'elle crée et supprime.
    { role: "dbOwner", db: "boutique_test" }
  ]
});

print("utilisateur applicatif 'app' créé sur boutique et boutique_test");
