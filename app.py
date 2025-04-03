from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
from pymongo import MongoClient
from bson.objectid import ObjectId
import os

# Inicialización de la aplicación Flask
app = Flask(__name__)
app.secret_key = 'arquitectura'  # Clave secreta para manejar sesiones seguras

# Configuración de MongoDB
app.config['MONGO_URI'] = 'mongodb://localhost:27017/inventarios'
try:
    mongo = MongoClient(app.config['MONGO_URI'])
    db = mongo.get_database()
    print("Conexión a MongoDB establecida correctamente")
    print("Colecciones disponibles:", db.list_collection_names())
except Exception as e:
    print("Error al conectar con MongoDB:", str(e))

# Configuración del sistema de autenticación
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # Ruta a la que redirigir si no está autenticado

# Clase Usuario para manejar la autenticación
class Usuario(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])  # Convertir ObjectId a string
        self.nombre = user_data['nombre']
        self.contrasena = user_data['contrasena']
        self.rol = user_data['rol']  # Roles: empleado, admin, superadmin

# Función para cargar usuarios desde la base de datos
@login_manager.user_loader
def load_user(user_id):
    user_data = db.usuarios.find_one({'_id': ObjectId(user_id)})
    if not user_data:
        return None
    return Usuario(user_data)

# Filtro para formatear fechas en las plantillas HTML
def format_datetime(value, format='%Y-%m-%d %H:%M'):
    """Formatea objetos datetime para mostrarlos en las vistas"""
    if isinstance(value, datetime):
        return value.strftime(format)
    return value

app.jinja_env.filters['datetimeformat'] = format_datetime


# --------------------------------------------------
# RUTAS DE LA APLICACIÓN

@app.route('/')
def index():
    """Página principal que muestra el inventario o redirige según rol"""
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    # Admin y superadmin ven el inventario completo
    if current_user.rol in ['admin', 'superadmin']:
        productos = list(db.productos.find())
        return render_template('index.html', productos=productos)
    else:
        # Empleados son redirigidos a la vista de solo lectura
        return redirect(url_for('visualizar'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Maneja el inicio de sesión de usuarios"""
    if request.method == 'POST':
        nombre = request.form['nombre']
        contrasena = request.form['contrasena']
        usuario_data = db.usuarios.find_one({'nombre': nombre})

        # Verificar credenciales
        if usuario_data and usuario_data['contrasena'] == contrasena:
            usuario = Usuario(usuario_data)
            login_user(usuario)
            flash("Inicio de sesión exitoso", "success")
            
            # Redirigir según rol
            if usuario.rol in ['admin', 'superadmin']:
                return redirect(url_for('index'))
            else:
                return redirect(url_for('visualizar'))
        else:
            flash("Credenciales incorrectas", "error")
    return render_template('login.html')

@app.route('/registro', methods=['GET', 'POST'])
def registro():
    """Permite registrar nuevos usuarios (por defecto como empleados)"""
    if request.method == 'POST':
        usuario = {
            'nombre': request.form['nombre'],
            'contrasena': request.form['contrasena'],
            'rol': 'empleado'  # Rol por defecto
        }
        
        # Validar que el usuario no exista
        if db.usuarios.find_one({'nombre': usuario['nombre']}):
            flash("El nombre de usuario ya existe", "error")
            return redirect(url_for('registro'))
        
        db.usuarios.insert_one(usuario)
        flash("Usuario registrado correctamente", "success")
        return redirect(url_for('login'))
    return render_template('registro.html')

@app.route('/asignar_rol/<user_id>', methods=['GET', 'POST'])
@login_required
def asignar_rol(user_id):
    """Permite a superadmins cambiar roles de usuarios"""
    if current_user.rol != 'superadmin':
        flash("No tienes permisos para acceder a esta página", "error")
        return redirect(url_for('index'))

    usuario = db.usuarios.find_one({'_id': ObjectId(user_id)})
    if not usuario:
        flash("Usuario no encontrado", "error")
        return redirect(url_for('lista_usuarios'))

    if request.method == 'POST':
        nuevo_rol = request.form['rol']
        db.usuarios.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'rol': nuevo_rol}}
        )
        flash(f"Rol actualizado a {nuevo_rol}", "success")
        return redirect(url_for('lista_usuarios'))

    return render_template('asignar_rol.html', usuario=usuario)

@app.route('/transacciones')
@login_required
def transacciones():
    """Muestra el historial de transacciones con opción de filtrado"""
    tipo_filtro = request.args.get('tipo', '')
    
    # Construir consulta basada en filtros
    query = {}
    if tipo_filtro:
        query['tipo'] = tipo_filtro
    
    transacciones = list(db.transacciones.find(query).sort('fecha', -1))
    
    # Enriquecer datos de transacciones con información de productos
    transacciones_pobladas = []
    for trans in transacciones:
        if trans['tipo'] in ['entrada', 'salida']:
            producto = db.productos.find_one({'_id': trans['producto_id']})
            trans['producto'] = {
                'nombre': producto['nombre'] if producto else 'Producto eliminado'
            }
        elif trans['tipo'] == 'eliminación':
            trans['producto'] = {'nombre': trans.get('producto_nombre', 'Producto eliminado')}
        
        transacciones_pobladas.append(trans)
    
    return render_template('transacciones.html', 
                         transacciones=transacciones_pobladas,
                         tipo_seleccionado=tipo_filtro)

@app.route('/add', methods=['GET', 'POST'])
@login_required
def add_product():
    """Agrega nuevos productos al inventario"""
    if current_user.rol not in ['admin', 'superadmin']:
        flash("No tienes permisos para acceder a esta página", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        producto = {
            'nombre': request.form['nombre'],
            'descripcion': request.form.get('descripcion', ''),
            'categoria': request.form['categoria'],
            'precio': float(request.form['precio']),
            'stock': int(request.form['stock'])
        }
        
        # Insertar producto y registrar transacción
        producto_id = db.productos.insert_one(producto).inserted_id
        
        transaccion = {
            'tipo': "entrada",
            'fecha': datetime.now(),
            'producto_id': producto_id,
            'cantidad': int(request.form['stock']),
            'usuario': current_user.nombre  # Registrar quién hizo la acción
        }
        db.transacciones.insert_one(transaccion)

        flash("Producto agregado correctamente", "success")
        return redirect(url_for('index'))
    
    return render_template('add_product.html')

@app.route('/update/<product_id>', methods=['GET', 'POST'])
@login_required
def update_product(product_id):
    """Actualiza la información de un producto existente"""
    # Validar ID del producto
    if not ObjectId.is_valid(product_id):
        flash("ID de producto inválido", "error")
        return redirect(url_for('index'))

    producto = db.productos.find_one({'_id': ObjectId(product_id)})
    if not producto:
        flash("Producto no encontrado", "error")
        return redirect(url_for('index'))

    if request.method == 'POST':
        try:
            nuevo_stock = int(request.form['stock'])
            diferencia = nuevo_stock - producto['stock']
            
            # Actualizar stock en la base de datos
            db.productos.update_one(
                {'_id': ObjectId(product_id)},
                {'$set': {'stock': nuevo_stock}}
            )
            
            # Registrar transacción si hubo cambio en el stock
            if diferencia != 0:
                tipo = "entrada" if diferencia > 0 else "salida"
                transaccion = {
                    'tipo': tipo,
                    'fecha': datetime.now(),
                    'producto_id': ObjectId(product_id),
                    'cantidad': abs(diferencia),
                    'usuario': current_user.nombre
                }
                db.transacciones.insert_one(transaccion)
            
            flash("Producto actualizado correctamente", "success")
            return redirect(url_for('index'))
            
        except ValueError:
            flash("El stock debe ser un número entero válido", "error")
        except Exception as e:
            flash(f"Error al actualizar: {str(e)}", "error")
    
    return render_template('update_product.html', producto=producto)

@app.route('/delete/<product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    """Elimina un producto del inventario y registra la transacción"""
    try:
        producto = db.productos.find_one({'_id': ObjectId(product_id)})
        if not producto:
            flash("Producto no encontrado", "error")
            return redirect(url_for('index'))

        # Registrar transacción de eliminación
        transaccion = {
            'tipo': 'eliminación',
            'fecha': datetime.now(),
            'producto_id': ObjectId(product_id),
            'cantidad': producto['stock'],
            'producto_nombre': producto['nombre'],
            'usuario': current_user.nombre
        }
        db.transacciones.insert_one(transaccion)

        # Eliminar el producto
        db.productos.delete_one({'_id': ObjectId(product_id)})
        flash("Producto eliminado correctamente", "success")
        return redirect(url_for('index'))

    except Exception as e:
        flash(f"Error al eliminar producto: {str(e)}", "error")
        return redirect(url_for('index'))
    
@app.route('/eliminar_usuario/<user_id>')
@login_required
def eliminar_usuario(user_id):
    """Elimina un usuario (solo para superadmins)"""
    if current_user.rol != 'superadmin':
        flash("No tienes permisos para acceder a esta página", "error")
        return redirect(url_for('index'))

    db.usuarios.delete_one({'_id': ObjectId(user_id)})
    flash("Usuario eliminado correctamente", "success")
    return redirect(url_for('lista_usuarios'))

@app.route('/usuarios')
@login_required
def lista_usuarios():
    """Muestra lista de usuarios (solo para superadmins)"""
    if current_user.rol != 'superadmin':
        flash("No tienes permisos para acceder a esta página", "error")
        return redirect(url_for('index'))

    usuarios = list(db.usuarios.find())
    return render_template('lista_usuarios.html', usuarios=usuarios)

@app.route('/visualizar')
@login_required
def visualizar():
    """Vista de solo lectura para empleados"""
    if current_user.rol not in ['empleado']:
        flash("No tienes permisos para acceder a esta página", "error")
        return redirect(url_for('index'))

    productos = list(db.productos.find())
    return render_template('visualizar.html', productos=productos)

@app.route('/logout')
@login_required
def logout():
    """Cierra la sesión del usuario"""
    logout_user()
    flash("Sesión cerrada correctamente", "success")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)