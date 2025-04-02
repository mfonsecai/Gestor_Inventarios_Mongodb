from app import app, db
from bson.objectid import ObjectId

def crear_superadmin():
    # Verificar si ya existe un superadmin
    superadmin = db.usuarios.find_one({'rol': 'superadmin'})
    if superadmin:
        print("Ya existe un superadmin.")
        return

    # Crear el superadmin
    superadmin = {
        'nombre': "Felipe C",
        'contrasena': "123456",  # Cambia esto por una contraseña segura
        'rol': 'superadmin'
    }
    db.usuarios.insert_one(superadmin)
    print("Superadmin creado correctamente.")

if __name__ == '__main__':
    with app.app_context():
        crear_superadmin()