from functools import wraps
from flask import Flask, request, jsonify
import psycopg2
import psycopg2.extras
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone, date
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

app.config['SECRET_KEY'] = 'Secret_Key'

# -------------------- Conexión a PostgreSQL --------------------
def conectar():
    return psycopg2.connect(
        host="localhost",
        port="5432",
        database="EsportsCanarias",
        user="postgres",
        password="postgres"
    )

# -------------------- Ejecutar SQL --------------------
def ejecutar_sql(sql, params=None):
    try:
        conn = conectar()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if params:
            cur.execute(sql, params)
        else:
            cur.execute(sql)

        if sql.strip().lower().startswith("select"):
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        else:
            if "returning" in sql.lower():
                rows = cur.fetchall()
                conn.commit()  # <-- Esto es lo que faltaba
                cur.close()
                conn.close()
                return rows
            else:
                conn.commit()
                cur.close()
                conn.close()
                return {"msg": "Operación exitosa"}
    except Exception as e:
        print(f"Error en ejecutar_sql: {e}")
        return {"error": str(e)}



def ejecutar_sql_params(sql, params=None):
    try:
        conn = conectar()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        if sql.strip().lower().startswith("select"):
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        else:
            conn.commit()
            cur.close()
            conn.close()
            return None
    except Exception as e:
        print("Error ejecutar_sql:", e)
        raise e

# -------------------- Decorador de Autenticación --------------------
def token_required(f):
    @wraps(f)
    def decorador(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token faltante'}), 401
        try:
            token = token.replace('Bearer ', '')
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            usuario = data['usuario']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expirado'}), 401
        except Exception as e:
            return jsonify({'error': f'Token inválido: {str(e)}'}), 401
        return f(usuario, *args, **kwargs)
    return decorador

def admin_required(f):
    @token_required
    @wraps(f)
    def decorador(usuario, *args, **kwargs):
        if usuario['rol'] != 'administrador':
            return jsonify({'error': 'Acceso restringido a administradores'}), 403
        return f(usuario, *args, **kwargs)
    return decorador

# -------------------- Rutas Públicas --------------------
@app.route('/usuario/login', methods=['POST'])
def login():
    data = request.get_json()
    print('JSON recibido:', data)
    email = data.get('email')
    password = data.get('password')

    if not email:
        return jsonify({'error': 'El email es requerido'}), 400
    if not password:
        return jsonify({'error': 'La contraseña es requerida'}), 400

    usuario = ejecutar_sql('SELECT * FROM "Usuario" WHERE email = %s', (email,))
    print('Resultado ejecutar_sql:', usuario)

    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404

    if isinstance(usuario, list):
        usuario = usuario[0]

    usuario = dict(usuario)  # por si acaso

    contrasena_hash = usuario.get('contraseña')
    print(f"contraseña hash: {contrasena_hash} (tipo: {type(contrasena_hash)})")

    if contrasena_hash is None:
        return jsonify({'error': 'Error interno: hash de contraseña no encontrado'}), 500

    if not bcrypt.checkpw(password.encode('utf-8'), contrasena_hash.encode('utf-8')):
        return jsonify({'error': 'Contraseña incorrecta'}), 401

    token = jwt.encode({
        'usuario': {
            'id': usuario['id_usuario'],
            'nombre': usuario['nombre'],
            'rol': usuario['rol'],
            'email': usuario['email']
        },
        'exp': datetime.now(timezone.utc) + timedelta(hours=12)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({
        'token': token,
        'usuario': {
            'id': usuario['id_usuario'],
            'nombre': usuario['nombre'],
            'rol': usuario['rol'],
            'email': usuario['email']
        }
    }), 200


@app.route('/usuario/registro', methods=['POST'])
def registrar_usuario():
    data = request.json
    nombre = data['nombre']
    email = data['email']
    contraseña_plana = data['contraseña']
    rol = 'jugador'
    hashed = bcrypt.hashpw(contraseña_plana.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Insertar usuario
    sql_usuario = 'INSERT INTO "Usuario" (nombre, email, contraseña, rol) VALUES (%s, %s, %s, %s) RETURNING id_usuario'
    result_usuario = ejecutar_sql(sql_usuario, (nombre, email, hashed, rol))

    if not result_usuario or "error" in result_usuario:
        return jsonify({'error': 'Error al crear el usuario'}), 500

    id_usuario = result_usuario[0]['id_usuario']

    # Obtener todos los juegos individuales
    sql_juegos = 'SELECT id_juego FROM "Juego" WHERE es_individual = TRUE'
    juegos_individuales = ejecutar_sql(sql_juegos)

    # Insertar en JugadorIndividual
    for juego in juegos_individuales:
        id_juego = juego['id_juego']
        sql_insert_jugador = """
            INSERT INTO "JugadorIndividual" (id_usuario, id_juego, victorias, derrotas)
            VALUES (%s, %s, 0, 0)
        """
        resultado_insert = ejecutar_sql(sql_insert_jugador, (id_usuario, id_juego))
        print(f"Resultado insert jugador individual: {resultado_insert}")

    # Crear token
    token = jwt.encode({
        'usuario': {
            'id': id_usuario,
            'nombre': nombre,
            'rol': rol,
            'email': email
        },
        'exp': datetime.now(timezone.utc) + timedelta(hours=12)
    }, app.config['SECRET_KEY'], algorithm='HS256')

    return jsonify({
        'token': token,
        'usuario': {
            'id': id_usuario,
            'nombre': nombre,
            'rol': rol,
            'email': email
        }
    }), 200




@app.route('/torneos', methods=['GET'])
def obtener_torneos():
    datos = ejecutar_sql('SELECT * FROM "Torneo"')
    return jsonify(datos)

@app.route('/eventos', methods=['GET'])
def obtener_eventos():
    datos = ejecutar_sql('SELECT * FROM "Evento"')
    return jsonify(datos)

@app.route('/equipos', methods=['GET'])
def obtener_equipos():
    datos = ejecutar_sql('SELECT * FROM "Equipo"')
    return jsonify(datos)

@app.route('/equipos/por-juego/<int:id_juego>', methods=['GET'])
def obtener_equipos_por_juego(id_juego):
    sql = '''
        SELECT DISTINCT e.id_equipo, e.nombre, e.victorias, e.derrotas
        FROM "Equipo" e
        JOIN "EquipoTorneo" et ON e.id_equipo = et.equipo_id
        JOIN "Torneo" t ON et.torneo_id = t.id_torneo
        WHERE t.id_juego = %s
    '''
    datos = ejecutar_sql(sql, (id_juego,))
    return jsonify(datos)

@app.route('/jugadores/por-juego/<int:id_juego>', methods=['GET'])
def obtener_jugadores_por_juego(id_juego):
    sql = '''
        SELECT DISTINCT u.id_usuario, u.nombre, ji.victorias, ji.derrotas
        FROM "Usuario" u
        JOIN "JugadorIndividual" ji ON u.id_usuario = ji.id_usuario
        JOIN "Juego" j ON ji.id_juego = j.id_juego
        WHERE j.id_juego = %s AND j.es_individual = TRUE
        ORDER BY ji.victorias DESC
    '''
    datos = ejecutar_sql(sql, (id_juego,))
    return jsonify(datos)

@app.route('/juegos', methods=['GET'])
def obtener_juegos():
    tipo = request.args.get('tipo')
    if tipo == 'equipo':
        datos = ejecutar_sql('SELECT * FROM "Juego" WHERE es_individual = FALSE')
    elif tipo == 'individual':
        datos = ejecutar_sql('SELECT * FROM "Juego" WHERE es_individual = TRUE')
    else:
        datos = ejecutar_sql('SELECT * FROM "Juego"')
    return jsonify(datos)

@app.route('/torneos/por-juego/<int:id_juego>', methods=['GET'])
def obtener_torneos_por_juego(id_juego):
    sql = '''
        SELECT *
        FROM "Torneo"
        WHERE id_juego = %s
        ORDER BY fecha_inicio DESC
    '''
    datos = ejecutar_sql(sql, (id_juego,))
    return jsonify(datos)


@app.route('/clasificacion/<int:torneo_id>', methods=['GET'])
def clasificacion_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT c.id_clasificacion, c.puntos, c.posicion,
               u.nombre AS usuario, eq.nombre AS equipo
        FROM "Clasificacion" c
        LEFT JOIN "Usuario" u ON c.id_usuario = u.id_usuario
        LEFT JOIN "Equipo" eq ON c.id_equipo = eq.id_equipo
        WHERE c.id_torneo = %s
        ORDER BY c.posicion ASC
    ''', (torneo_id,))
    return jsonify(datos)

@app.route('/torneo/<int:torneo_id>/equipos', methods=['GET'])
def equipos_en_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT e.id_equipo, e.nombre
        FROM "EquipoTorneo" et
        JOIN "Equipo" e ON et.equipo_id = e.id_equipo
        WHERE et.torneo_id = %s
    ''', (torneo_id,))
    return jsonify(datos)

@app.route('/torneo/<int:torneo_id>/jugadores', methods=['GET'])
def jugadores_en_torneo(torneo_id):
    datos = ejecutar_sql('''
        SELECT u.id_usuario, u.nombre
        FROM "UsuarioTorneo" ut
        JOIN "Usuario" u ON ut.usuario_id = u.id_usuario
        WHERE ut.torneo_id = %s
    ''', (torneo_id,))
    return jsonify(datos)

# -------------------- Rutas Protegidas --------------------
@app.route('/equipo/crear', methods=['POST'])
@token_required
def crear_equipo():
    data = request.json
    nombre = data['nombre']
    id_fundador = data['id_capitan']
    fecha_creacion = date.today()
    sql = 'INSERT INTO "Equipo" (nombre, fundador, fecha_creacion) VALUES (%s, %s, %s)'
    ejecutar_sql(sql, (nombre, id_fundador, fecha_creacion))
    return jsonify({'mensaje': 'Equipo creado correctamente'})

@app.route('/torneo/crear', methods=['POST'])
@token_required
@admin_required
def crear_torneo():
    data = request.json
    nombre = data['nombre']
    fecha_inicio = data['fecha_inicio']
    fecha_fin = data['fecha_fin']
    ubicacion = data['ubicacion']
    id_evento = data['id_evento']
    id_juego = data['id_juego']
    sql = '''
        INSERT INTO "Torneo" (nombre, fecha_inicio, fecha_fin, ubicacion, id_evento, id_juego)
        VALUES (%s, %s, %s, %s, %s, %s)
    '''
    ejecutar_sql(sql, (nombre, fecha_inicio, fecha_fin, ubicacion, id_evento, id_juego))
    return jsonify({'mensaje': 'Torneo creado correctamente'})

@app.route('/evento/crear', methods=['POST'])
def crear_evento():
    datos = request.json
    nombre = datos.get('nombre')
    tipo = datos.get('tipo')
    año = datos.get('año')
    mes = datos.get('mes')

    if tipo not in ['anual', 'mensual']:
        return jsonify({'error': 'Tipo de evento no válido. Debe ser "anual" o "mensual".'}), 400

    if tipo == 'anual' and not año:
        return jsonify({'error': 'El campo año es obligatorio para eventos anuales'}), 400
    if tipo == 'mensual' and (not año or not mes):
        return jsonify({'error': 'Los campos año y mes son obligatorios para eventos mensuales'}), 400

    sql = """
        INSERT INTO Evento (nombre, tipo, año, mes)
        VALUES (%s, %s, %s, %s)
        RETURNING *;
    """
    resultado = ejecutar_sql(sql, (nombre, tipo, año, mes))
    return jsonify(resultado), 201


@app.route('/equipos/fundador/<int:id_fundador>', methods=['GET'])
def obtener_equipos_por_fundador(id_fundador):
    sql = "SELECT * FROM Equipo WHERE id_fundador = %s"
    resultado = ejecutar_sql(sql, (id_fundador,))
    return jsonify(resultado), 200

@app.route('/usuarios/<int:id_usuario>', methods=['PUT'])
@token_required
def editar_usuario(usuario, id_usuario):
    data = request.get_json()
    nombre = data.get("nombre")
    correo = data.get("correo")
    password = data.get("password")

    campos = []
    valores = []

    if nombre:
        campos.append('"nombre" = %s')
        valores.append(nombre)
    if correo:
        campos.append('"email" = %s')
        valores.append(correo)
    if password:
        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        campos.append('"contraseña" = %s')
        valores.append(hashed_pw)

    if not campos:
        return jsonify({"error": "No se proporcionaron campos a actualizar"}), 400

    sql_update = f'UPDATE "Usuario" SET {", ".join(campos)} WHERE id_usuario = %s'
    valores.append(id_usuario)
    resultado = ejecutar_sql(sql_update, valores)

    if "error" in resultado:
        return jsonify({"error": "Error al actualizar el usuario"}), 500

    sql_select = 'SELECT id_usuario, nombre, email, rol FROM "Usuario" WHERE id_usuario = %s'
    usuario_actualizado = ejecutar_sql(sql_select, (id_usuario,))
    usuario = usuario_actualizado[0]
    usuario["id"] = usuario.pop("id_usuario")
    return jsonify(usuario), 200


@app.route('/torneo/<int:torneo_id>/clasificacion', methods=['POST'])
@token_required
def registrar_clasificacion(torneo_id):
    data = request.json
    puntos = data['puntos']
    posicion = data['posicion']
    id_usuario = data.get('id_usuario')
    id_equipo = data.get('id_equipo')
    sql = '''
        INSERT INTO "Clasificacion" (id_torneo, puntos, posicion, id_usuario, id_equipo)
        VALUES (%s, %s, %s, %s, %s)
    '''
    ejecutar_sql(sql, (torneo_id, puntos, posicion, id_usuario, id_equipo))
    return jsonify({'mensaje': 'Clasificación registrada correctamente'})


@app.route('/torneo/<int:torneo_id>/unirse', methods=['POST'])
@token_required
def unirse_torneo(usuario, torneo_id):
    id_usuario = usuario['id']

    # Verificar que el torneo existe y es individual
    juego = ejecutar_sql(
        '''
        SELECT j.es_individual FROM "Torneo" t
        JOIN "Juego" j ON t.id_juego = j.id_juego
        WHERE t.id_torneo = %s
        ''', (torneo_id,)
    )
    if not juego:
        return jsonify({'error': 'Torneo no encontrado'}), 404
    if not juego[0]['es_individual']:
        return jsonify({'error': 'Este torneo no es individual'}), 400

    # Verificar que el usuario es jugador individual en ese juego
    jugador_individual = ejecutar_sql(
        'SELECT * FROM "JugadorIndividual" WHERE id_usuario = %s AND id_juego = (SELECT id_juego FROM "Torneo" WHERE id_torneo = %s)',
        (id_usuario, torneo_id)
    )
    if not jugador_individual:
        return jsonify({'error': 'Solo jugadores individuales pueden unirse por este endpoint'}), 403

    # Verificar si ya está inscrito
    inscrito = ejecutar_sql(
        'SELECT * FROM "UsuarioTorneo" WHERE usuario_id = %s AND torneo_id = %s',
        (id_usuario, torneo_id)
    )
    if inscrito:
        return jsonify({'error': 'Ya estás inscrito en este torneo'}), 400

    # Insertar inscripción
    resultado = ejecutar_sql(
        'INSERT INTO "UsuarioTorneo" (usuario_id, torneo_id) VALUES (%s, %s)',
        (id_usuario, torneo_id)
    )
    if "error" in resultado:
        return jsonify({'error': 'Error al inscribirse en el torneo'}), 500

    return jsonify({'mensaje': 'Inscripción exitosa en el torneo'}), 201



@app.route('/torneo/<int:torneo_id>/salir', methods=['POST'])
@token_required
def salir_torneo(usuario, torneo_id):
    id_usuario = usuario['id']

    # Verificar que está inscrito
    inscrito = ejecutar_sql(
        'SELECT * FROM "UsuarioTorneo" WHERE usuario_id = %s AND torneo_id = %s',
        (id_usuario, torneo_id)
    )
    if not inscrito:
        return jsonify({'error': 'No estás inscrito en este torneo'}), 400

    # Borrar la inscripción
    resultado = ejecutar_sql(
        'DELETE FROM "UsuarioTorneo" WHERE usuario_id = %s AND torneo_id = %s',
        (id_usuario, torneo_id)
    )
    if "error" in resultado:
        return jsonify({'error': 'Error al salir del torneo'}), 500

    return jsonify({'mensaje': 'Has salido del torneo correctamente'}), 200

# -------------------- Main --------------------
if __name__ == '__main__':
    app.run(debug=True)
