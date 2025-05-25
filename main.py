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
        password="1234"
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
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email y contraseña son requeridos'}), 400

    usuario = ejecutar_sql('SELECT * FROM "Usuario" WHERE email = %s', (email,))
    if not usuario:
        return jsonify({'error': 'Usuario no encontrado'}), 404
    usuario = usuario[0]

    if not bcrypt.checkpw(password.encode('utf-8'), usuario['contraseña'].encode('utf-8')):
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
    })


@app.route('/usuario/registro', methods=['POST'])
def registrar_usuario():
    data = request.json
    nombre = data['nombre']
    email = data['email']
    contraseña_plana = data['contraseña']
    rol = 'jugador'
    hashed = bcrypt.hashpw(contraseña_plana.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    sql_usuario = 'INSERT INTO "Usuario" (nombre, email, contraseña, rol) VALUES (%s, %s, %s, %s) RETURNING id_usuario'
    result_usuario = ejecutar_sql(sql_usuario, (nombre, email, hashed, rol))
    if not result_usuario or "error" in result_usuario:
        return jsonify({'error': 'Error al crear el usuario'}), 500

    id_usuario = result_usuario[0]['id_usuario']

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
    })


@app.route('/torneos', methods=['GET'])
def obtener_torneos():

    datos = ejecutar_sql('SELECT * FROM "Torneo" ORDER BY fecha_inicio DESC')
    return jsonify(datos)



@app.route('/eventos', methods=['GET'])
def obtener_eventos():
    datos = ejecutar_sql('SELECT * FROM "Evento" ORDER BY año DESC')
    return jsonify(datos)

@app.route('/equipos', methods=['GET'])
def obtener_equipos():
    datos = ejecutar_sql('SELECT * FROM "Equipo"')
    return jsonify(datos)



@app.route('/equipos/por-juego/<int:id_juego>', methods=['GET'])
def obtener_equipos_por_juego(id_juego):
    # Ahora usamos et.id_torneo (la FK correcta) para relacionar equipos con torneos
    sql = '''
        SELECT DISTINCT e.id_equipo, e.nombre, e.victorias, e.derrotas
        FROM "Equipo" e
        JOIN "EquipoTorneo" et ON e.id_equipo = et.equipo_id
        JOIN "Torneo" t ON et.id_torneo = t.id_torneo
        WHERE t.id_juego = %s
    '''
    datos = ejecutar_sql(sql, (id_juego,))
    return jsonify(datos)

@app.route('/equipos/liga/<int:id_juego>', methods=['GET'])
def obtener_equipos_en_liga(id_juego):
    sql = '''
        SELECT e.id_equipo, e.nombre, e.victorias, e.derrotas
        FROM "Equipo" e
        JOIN "LigaEquipo" le ON e.id_equipo = le.id_equipo
        WHERE le.id_juego = %s
    '''
    datos = ejecutar_sql(sql, (id_juego,))
    return jsonify(datos)



@app.route('/jugadores/por-juego/<int:id_juego>', methods=['GET'])
def obtener_jugadores_por_juego(id_juego):
    sql = '''
        SELECT u.id_usuario, u.nombre
        FROM "Usuario" u
        JOIN "LigaIndividual" li ON u.id_usuario = li.id_usuario
        WHERE li.id_juego = %s
        ORDER BY u.nombre
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
    datos = ejecutar_sql('''
        SELECT * FROM "Torneo"
        WHERE id_juego = %s
        ORDER BY fecha_inicio DESC
    ''', (id_juego,))
    return jsonify(datos)

@app.route('/torneos/completos/<int:id_juego>', methods=['GET'])
def obtener_torneos_completos(id_juego):
    datos = ejecutar_sql('''
        SELECT t.id_torneo, t.nombre, t.fecha_inicio, t.fecha_fin, t.ubicacion,
               e.id_evento, e.nombre AS nombre_evento
        FROM "Torneo" t
        LEFT JOIN "Evento" e ON t.id_evento = e.id_evento
        WHERE t.id_juego = %s
        ORDER BY t.fecha_inicio DESC
    ''', (id_juego,))
    return jsonify(datos)

@app.route('/torneos/evento/<int:id_evento>', methods=['GET'])
def obtener_torneos_por_evento(id_evento):
    datos = ejecutar_sql('''
        SELECT t.id_torneo, t.nombre, t.fecha_inicio, t.fecha_fin, t.ubicacion,
               e.id_evento, e.nombre AS nombre_evento, t.id_juego
        FROM "Torneo" t
        LEFT JOIN "Evento" e ON t.id_evento = e.id_evento
        WHERE t.id_evento = %s
        ORDER BY t.fecha_inicio DESC
    ''', (id_evento,))
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

    if not datos:
        return jsonify({"message": "No hay clasificación para este torneo"}), 404

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

# -------------------- Rutas Privadas --------------------

@app.route('/usuario/perfil', methods=['GET'])
@token_required
def perfil(usuario):
    # usuario es el dict que viene del token (id, nombre, rol, email)
    return jsonify({
        "id": usuario['id'],
        "nombre": usuario['nombre'],
        "rol": usuario['rol'],
        "email": usuario['email']
    })

@app.route('/equipo/crear', methods=['POST'])
@token_required
def crear_equipo(usuario):
    data = request.json
    nombre = data['nombre']
    id_fundador = usuario['id']
    fecha_creacion = date.today()

    # Inserta el equipo y devuelve el id y código (asumiendo la DB genera el código automáticamente)
    sql = '''
        INSERT INTO "Equipo" (nombre, fundador, fecha_creacion)
        VALUES (%s, %s, %s)
        RETURNING id_equipo, codigo
    '''
    resultado = ejecutar_sql(sql, (nombre, id_fundador, fecha_creacion))

    if isinstance(resultado, dict) and "error" in resultado:
        return jsonify({'mensaje': 'Error al crear equipo', 'error': resultado['error']}), 500

    if resultado and len(resultado) > 0:
        id_equipo = resultado[0]['id_equipo']
        codigo = resultado[0]['codigo']

        # Añadimos al fundador como miembro
        ejecutar_sql('INSERT INTO "UsuarioEquipo" (usuario_id, equipo_id) VALUES (%s, %s)', (id_fundador, id_equipo))

        equipo_creado = {
            'id_equipo': id_equipo,
            'nombre': nombre,
            'fundador': id_fundador,
            'fecha_creacion': fecha_creacion.isoformat(),
            'codigo': codigo,
            'victorias': 0,
            'derrotas': 0
        }
        return jsonify(equipo_creado), 201
    else:
        return jsonify({'mensaje': 'No se pudo crear el equipo'}), 500


@app.route('/equipo/salirse', methods=['POST'])
@token_required
def salir_del_equipo(usuario):
    # Buscar equipo al que pertenece el usuario
    equipo_usuario = ejecutar_sql('SELECT equipo_id FROM "UsuarioEquipo" WHERE usuario_id = %s', (usuario['id'],))
    if not equipo_usuario or len(equipo_usuario) == 0:
        return jsonify({'mensaje': 'No perteneces a ningún equipo'}), 400

    id_equipo = equipo_usuario[0]['equipo_id']

    # Obtener fundador del equipo
    equipo = ejecutar_sql('SELECT fundador FROM "Equipo" WHERE id_equipo = %s', (id_equipo,))
    if not equipo or len(equipo) == 0:
        return jsonify({'mensaje': 'Equipo no encontrado'}), 404

    fundador_id = equipo[0]['fundador']

    if usuario['id'] == fundador_id:
        # Si es fundador, eliminar todos los usuarios de ese equipo y borrar el equipo
        ejecutar_sql('DELETE FROM "UsuarioEquipo" WHERE equipo_id = %s', (id_equipo,))
        ejecutar_sql('DELETE FROM "Equipo" WHERE id_equipo = %s', (id_equipo,))
        return jsonify({'mensaje': 'Te has salido y el equipo ha sido eliminado porque eras el fundador.'})
    else:
        # Si no es fundador, solo eliminar la relación de usuario con el equipo
        ejecutar_sql('DELETE FROM "UsuarioEquipo" WHERE usuario_id = %s AND equipo_id = %s', (usuario['id'], id_equipo))
        return jsonify({'mensaje': 'Te has salido del equipo correctamente.'})


@app.route('/equipo/usuario', methods=['GET'])
@token_required
def obtener_equipo_usuario(usuario):
    equipo = ejecutar_sql('''
        SELECT e.id_equipo, e.nombre, e.fundador, e.fecha_creacion, e.codigo, e.victorias, e.derrotas
        FROM "Equipo" e
        JOIN "UsuarioEquipo" ue ON e.id_equipo = ue.equipo_id
        WHERE ue.usuario_id = %s
    ''', (usuario['id'],))

    if equipo and len(equipo) > 0:
        return jsonify(equipo[0])
    else:
        return jsonify({}), 204  # No Content si no tiene equipo


@app.route('/equipo/<int:id_equipo>/miembros', methods=['GET'])
@token_required
def obtener_miembros_equipo(usuario, id_equipo):
    sql = '''
        SELECT u.id_usuario, u.nombre
        FROM "Usuario" u
        JOIN "UsuarioEquipo" ue ON u.id_usuario = ue.usuario_id
        WHERE ue.equipo_id = %s
    '''
    miembros = ejecutar_sql(sql, (id_equipo,))
    return jsonify(miembros)

@app.route('/equipo/codigo/<codigo>', methods=['GET'])
@token_required
def obtener_equipo_por_codigo(usuario, codigo):
    equipo = ejecutar_sql('''
        SELECT id_equipo, nombre, victorias, derrotas, fundador, fecha_creacion, codigo
        FROM "Equipo"
        WHERE codigo = %s
    ''', (codigo,))

    if equipo and len(equipo) > 0:
        # Devolvemos el primer (único) resultado
        return jsonify(equipo[0])
    else:
        return jsonify({'mensaje': 'Equipo no encontrado'}), 404


@app.route('/equipo/unirse/<codigo>', methods=['POST'])
@token_required
def unirse_equipo_por_codigo(usuario, codigo):
    equipo = ejecutar_sql('SELECT id_equipo FROM "Equipo" WHERE codigo = %s', (codigo,))
    if not equipo or len(equipo) == 0:
        return jsonify({'mensaje': 'Código de equipo no válido'}), 404

    # `equipo` es lista, así que accedes al primer elemento con [0]
    id_equipo = equipo[0]['id_equipo']

    pertenece = ejecutar_sql('SELECT * FROM "UsuarioEquipo" WHERE usuario_id = %s', (usuario['id'],))
    if pertenece and len(pertenece) > 0:
        return jsonify({'mensaje': 'Ya perteneces a un equipo'}), 400

    ejecutar_sql('INSERT INTO "UsuarioEquipo" (equipo_id, usuario_id) VALUES (%s, %s)', (id_equipo, usuario['id']))
    return jsonify({'mensaje': 'Te has unido al equipo correctamente'})



@app.route('/torneo/crear', methods=['POST'])
@admin_required
def crear_torneo(usuario):
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
@admin_required
def crear_evento(usuario):
    data = request.json
    nombre = data['nombre']
    tipo = data.get('tipo')
    if tipo not in ('anual', 'mensual'):
        return jsonify({'error': 'Tipo de evento inválido, debe ser "anual" o "mensual"'}), 400
    año = data.get('año')
    mes = data.get('mes') if tipo == 'mensual' else None

    sql = '''
        INSERT INTO "Evento" (nombre, tipo, año, mes)
        VALUES (%s, %s, %s, %s)
    '''
    ejecutar_sql(sql, (nombre, tipo, año, mes))
    return jsonify({'mensaje': 'Evento creado correctamente'})


@app.route('/usuarios/editar/<int:id_usuario>', methods=['PUT'])
@token_required
def editar_usuario(usuario, id_usuario):
    if usuario['rol'] != 'administrador' and usuario['id'] != id_usuario:
        return jsonify({'error': 'No tienes permisos para editar este usuario'}), 403

    data = request.json
    nombre = data.get('nombre')
    email = data.get('email')  # aquí espera 'email'
    contraseña = data.get('password')

    sql_set = []
    params = []

    if nombre:
        sql_set.append('nombre = %s')
        params.append(nombre)
    if email:
        sql_set.append('email = %s')
        params.append(email)
    if contraseña:
        hashed = bcrypt.hashpw(contraseña.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        sql_set.append('contraseña = %s')
        params.append(hashed)

    if not sql_set:
        return jsonify({'error': 'No hay datos para actualizar'}), 400

    params.append(id_usuario)
    sql = f'''
    UPDATE "Usuario" SET {", ".join(sql_set)} WHERE id_usuario = %s
    RETURNING id_usuario AS id, nombre, rol, email
    '''
    resultado = ejecutar_sql(sql, tuple(params))
    if not resultado or "error" in resultado:
        return jsonify({'error': 'Error al actualizar usuario'}), 500

    usuario_actualizado = resultado[0]
    return jsonify(usuario_actualizado)


@app.route('/inscribir/jugador', methods=['POST'])
@token_required
def inscribir_jugador(usuario):
    data = request.json
    if not data:
        return jsonify({'error': 'JSON inválido o no enviado'}), 400

    id_torneo = data.get('id_torneo')
    if not id_torneo:
        return jsonify({'error': 'Falta id_torneo'}), 400

    id_usuario = usuario['id']

    torneo = ejecutar_sql('SELECT * FROM "Torneo" WHERE id_torneo = %s', (id_torneo,))
    if not torneo:
        return jsonify({'error': 'Torneo no encontrado'}), 404
    torneo = torneo[0]

    juego = ejecutar_sql('SELECT * FROM "Juego" WHERE id_juego = %s', (torneo['id_juego'],))
    if not juego or not juego[0]['es_individual']:
        return jsonify({'error': 'Este torneo no es para jugadores individuales'}), 403

    # Verificar si ya está inscrito
    inscritos = ejecutar_sql(
        'SELECT * FROM "UsuarioTorneo" WHERE usuario_id = %s AND id_torneo = %s',
        (id_usuario, id_torneo)
    )
    if inscritos:
        return jsonify({'error': 'Jugador ya inscrito en este torneo'}), 405

    try:
        ejecutar_sql('INSERT INTO "UsuarioTorneo" (usuario_id, id_torneo) VALUES (%s, %s)', (id_usuario, id_torneo))

        # Insertar en Clasificacion con valores iniciales
        ejecutar_sql(
            '''INSERT INTO "Clasificacion" 
               (id_torneo, id_equipo, id_usuario, puntos, posicion)
               VALUES (%s, %s, %s, %s, %s)''',
            (id_torneo, None, id_usuario, 0, None)
        )
    except Exception as e:
        return jsonify({'error': f'Error al inscribir jugador: {str(e)}'}), 500

    return jsonify({'mensaje': 'Jugador inscrito en torneo'}), 201


@app.route('/torneo/<int:torneo_id>/salir', methods=['POST'])
@token_required
def salir_torneo(usuario, torneo_id):
    id_usuario = usuario['id']

    torneo = ejecutar_sql('SELECT * FROM "Torneo" WHERE id_torneo = %s', (torneo_id,))
    if not torneo:
        return jsonify({'error': 'Torneo no encontrado'}), 404

    inscritos = ejecutar_sql(
        'SELECT * FROM "UsuarioTorneo" WHERE usuario_id = %s AND id_torneo = %s',
        (id_usuario, torneo_id)
    )
    if not inscritos:
        return jsonify({'error': 'No estás inscrito en este torneo'}), 400

    try:
        ejecutar_sql('DELETE FROM "UsuarioTorneo" WHERE usuario_id = %s AND id_torneo = %s', (id_usuario, torneo_id))
        ejecutar_sql('DELETE FROM "Clasificacion" WHERE id_usuario = %s AND id_torneo = %s', (id_usuario, torneo_id))
    except Exception as e:
        return jsonify({'error': f'Error al salir del torneo: {str(e)}'}), 500

    return jsonify({'mensaje': 'Saliste del torneo correctamente'})

@app.route('/unirse/juego-individual', methods=['POST'])
@token_required
def unirse_juego_individual(usuario):
    data = request.json
    if not data or 'id_juego' not in data:
        return jsonify({'error': 'Falta id_juego'}), 400

    id_usuario = usuario['id']
    id_juego = data['id_juego']

    # Verificar que el juego es individual
    juego = ejecutar_sql('SELECT * FROM "Juego" WHERE id_juego = %s', (id_juego,))
    if not juego:
        return jsonify({'error': 'Juego no encontrado'}), 404
    if not juego[0]['es_individual']:
        return jsonify({'error': 'El juego no es individual'}), 400

    # Verificar si ya está inscrito en ese juego
    ya_inscrito = ejecutar_sql('SELECT * FROM "LigaIndividual" WHERE id_usuario = %s AND id_juego = %s', (id_usuario, id_juego))
    if ya_inscrito:
        return jsonify({'error': 'Ya estás inscrito en este juego individual'}), 409

    # Insertar inscripción
    try:
        ejecutar_sql('INSERT INTO "LigaIndividual" (id_usuario, id_juego) VALUES (%s, %s)', (id_usuario, id_juego))
    except Exception as e:
        return jsonify({'error': f'Error al inscribirse en el juego individual: {str(e)}'}), 500

    return jsonify({'mensaje': 'Inscripción al juego individual realizada correctamente'}), 201

@app.route('/salir/juego-individual', methods=['POST'])
@token_required
def salir_juego_individual(usuario):
    data = request.json
    if not data or 'id_juego' not in data:
        return jsonify({'error': 'Falta id_juego'}), 400

    id_usuario = usuario['id']
    id_juego = data['id_juego']

    # Verificar que el juego es individual
    juego = ejecutar_sql('SELECT * FROM "Juego" WHERE id_juego = %s', (id_juego,))
    if not juego:
        return jsonify({'error': 'Juego no encontrado'}), 404
    if not juego[0]['es_individual']:
        return jsonify({'error': 'El juego no es individual'}), 400

    # Verificar si está inscrito en ese juego
    inscrito = ejecutar_sql('SELECT * FROM "LigaIndividual" WHERE id_usuario = %s AND id_juego = %s', (id_usuario, id_juego))
    if not inscrito:
        return jsonify({'error': 'No estás inscrito en este juego individual'}), 409

    # Eliminar inscripción
    try:
        ejecutar_sql('DELETE FROM "LigaIndividual" WHERE id_usuario = %s AND id_juego = %s', (id_usuario, id_juego))
    except Exception as e:
        return jsonify({'error': f'Error al salir del juego individual: {str(e)}'}), 500

    return jsonify({'mensaje': 'Has salido correctamente del juego individual'}), 200

@app.route('/equipo/fundador/<int:id_usuario>', methods=['GET'])
@token_required
def get_equipo_por_fundador(usuario, id_usuario):
    # Verificamos que el usuario autenticado sea el mismo que el solicitado
    if usuario.get('id') != id_usuario:
        return jsonify({'error': 'No autorizado para ver este equipo'}), 403

    try:
        equipo = ejecutar_sql(
            'SELECT * FROM "Equipo" WHERE fundador = %s',
            (id_usuario,)
        )
        if not equipo:
            return jsonify({'mensaje': 'No se encontró equipo para este usuario'}), 404

        return jsonify(equipo[0]), 200

    except Exception as e:
        return jsonify({'error': f'Error al obtener equipo del fundador: {str(e)}'}), 500


@app.route('/inscribir/equipo', methods=['POST'])
@token_required
def inscribir_equipo(usuario):
    data = request.json
    id_torneo = data.get('id_torneo')
    id_equipo = data.get('id_equipo')

    if not id_torneo or not id_equipo:
        return jsonify({'error': 'Faltan datos obligatorios (id_torneo, id_equipo)'}), 400

    torneo = ejecutar_sql('SELECT * FROM "Torneo" WHERE id_torneo = %s', (id_torneo,))
    if not torneo:
        return jsonify({'error': 'Torneo no encontrado'}), 404
    torneo = torneo[0]

    juego = ejecutar_sql('SELECT * FROM "Juego" WHERE id_juego = %s', (torneo['id_juego'],))
    if not juego or juego[0]['es_individual']:
        return jsonify({'error': 'Este torneo no es para equipos'}), 400

    equipo = ejecutar_sql('SELECT * FROM "Equipo" WHERE id_equipo = %s', (id_equipo,))
    if not equipo:
        return jsonify({'error': 'Equipo no encontrado'}), 404

    if equipo[0]['fundador'] != usuario['id']:
        return jsonify({'error': 'Solo el fundador del equipo puede inscribirlo'}), 403

    ya_inscrito = ejecutar_sql('SELECT * FROM "EquipoTorneo" WHERE equipo_id = %s AND id_torneo = %s', (id_equipo, id_torneo))
    if ya_inscrito:
        return jsonify({'error': 'El equipo ya está inscrito en este torneo'}), 400

    try:
        ejecutar_sql('INSERT INTO "EquipoTorneo" (equipo_id, id_torneo) VALUES (%s, %s)', (id_equipo, id_torneo))

        # Insertar en Clasificacion para el equipo
        ejecutar_sql(
            '''INSERT INTO "Clasificacion" (id_torneo, id_equipo, id_usuario, puntos, posicion)
               VALUES (%s, %s, %s, %s, %s)''',
            (id_torneo, id_equipo, None, 0, None)
        )
    except Exception as e:
        return jsonify({'error': f'Error al inscribir equipo: {str(e)}'}), 500

    return jsonify({'mensaje': 'Equipo inscrito en torneo'}), 200


@app.route('/unirse/juego-equipo', methods=['POST'])
@token_required
def unirse_juego_equipo(usuario):
    print("Usuario recibido:", usuario)

    data = request.json
    id_juego = data.get('id_juego')
    id_equipo = data.get('id_equipo')

    if not id_juego or not id_equipo:
        return jsonify({'error': 'Faltan datos obligatorios (id_juego, id_equipo)'}), 400

    juego = ejecutar_sql('SELECT * FROM "Juego" WHERE id_juego = %s', (id_juego,))
    if not juego:
        return jsonify({'error': 'Juego no encontrado'}), 404
    if juego[0]['es_individual']:
        return jsonify({'error': 'Este juego no es para equipos'}), 400

    print(f"id_equipo recibido: {id_equipo}, tipo: {type(id_equipo)}")
    equipo = ejecutar_sql('SELECT fundador FROM "Equipo" WHERE id_equipo = %s', (id_equipo,))
    print(f"Resultado fundador:", equipo)

    if not equipo:
        return jsonify({'error': 'Equipo no encontrado'}), 404

    fundador = equipo[0]['fundador']
    print(f"Fundador en BD: {fundador}, Usuario ID: {usuario.get('id')}")

    if fundador != usuario.get('id'):
        return jsonify({'error': 'Solo el fundador del equipo puede unirlo a una liga'}), 403

    ya_inscrito = ejecutar_sql(
        'SELECT * FROM "LigaEquipo" WHERE id_equipo = %s AND id_juego = %s',
        (id_equipo, id_juego)
    )
    if ya_inscrito:
        return jsonify({'error': 'Este equipo ya está inscrito en la liga de este juego'}), 409

    try:
        print("Antes:",
              ejecutar_sql('SELECT * FROM "LigaEquipo" WHERE id_equipo = %s AND id_juego = %s', (id_equipo, id_juego)))
        ejecutar_sql(
            'INSERT INTO "LigaEquipo" (id_equipo, id_juego) VALUES (%s, %s)',
            (id_equipo, id_juego)
        )
        print("Después:",
              ejecutar_sql('SELECT * FROM "LigaEquipo" WHERE id_equipo = %s AND id_juego = %s', (id_equipo, id_juego)))


    except Exception as e:
        return jsonify({'error': f'Error al inscribir equipo en la liga: {str(e)}'}), 500

    return jsonify({'mensaje': 'Equipo inscrito en la liga correctamente'}), 201

@app.route('/salir/juego-equipo', methods=['POST'])
@token_required
def salir_juego_equipo(usuario):
    data = request.json
    if not data or 'id_juego' not in data or 'id_equipo' not in data:
        return jsonify({'error': 'Faltan datos (id_juego, id_equipo)'}), 400

    id_juego = data['id_juego']
    id_equipo = data['id_equipo']

    # Verificar que el juego es para equipos
    juego = ejecutar_sql('SELECT * FROM "Juego" WHERE id_juego = %s', (id_juego,))
    if not juego:
        return jsonify({'error': 'Juego no encontrado'}), 404
    if juego[0]['es_individual']:
        return jsonify({'error': 'El juego no es para equipos'}), 400

    # Verificar que el usuario es el fundador del equipo
    equipo = ejecutar_sql('SELECT * FROM "Equipo" WHERE id_equipo = %s', (id_equipo,))
    if not equipo:
        return jsonify({'error': 'Equipo no encontrado'}), 404
    if equipo[0]['fundador'] != usuario['id']:
        return jsonify({'error': 'Solo el fundador del equipo puede retirarlo de la liga'}), 403

    # Verificar si está inscrito
    inscrito = ejecutar_sql(
        'SELECT * FROM "LigaEquipo" WHERE id_equipo = %s AND id_juego = %s',
        (id_equipo, id_juego)
    )
    if not inscrito:
        return jsonify({'error': 'El equipo no está inscrito en este juego'}), 409

    try:
        ejecutar_sql('DELETE FROM "LigaEquipo" WHERE id_equipo = %s AND id_juego = %s', (id_equipo, id_juego))
    except Exception as e:
        return jsonify({'error': f'Error al salir del juego de equipos: {str(e)}'}), 500

    return jsonify({'mensaje': 'El equipo ha salido correctamente de la liga'}), 200


@app.route('/torneo-equipo/<int:id_torneo>/salir', methods=['POST'])
@token_required
def salir_torneo_equipo(usuario, id_torneo):
    data = request.json
    id_equipo = data.get('id_equipo')
    if not id_equipo:
        return jsonify({'error': 'Falta id_equipo'}), 400

    # Verificar que el torneo existe
    torneo = ejecutar_sql('SELECT * FROM "Torneo" WHERE id_torneo = %s', (id_torneo,))
    if not torneo:
        return jsonify({'error': 'Torneo no encontrado'}), 404

    # Verificar que el usuario es el fundador del equipo
    equipo = ejecutar_sql('SELECT * FROM "Equipo" WHERE id_equipo = %s', (id_equipo,))
    if not equipo:
        return jsonify({'error': 'Equipo no encontrado'}), 404
    if equipo[0]['fundador'] != usuario['id']:
        return jsonify({'error': 'Solo el fundador del equipo puede retirarlo del torneo'}), 403

    # Verificar inscripción
    inscritos = ejecutar_sql(
        'SELECT * FROM "EquipoTorneo" WHERE equipo_id = %s AND id_torneo = %s',
        (id_equipo, id_torneo)
    )
    if not inscritos:
        return jsonify({'error': 'El equipo no está inscrito en este torneo'}), 400

    try:
        ejecutar_sql('DELETE FROM "EquipoTorneo" WHERE equipo_id = %s AND id_torneo = %s', (id_equipo, id_torneo))
        ejecutar_sql('DELETE FROM "Clasificacion" WHERE id_equipo = %s AND id_torneo = %s', (id_equipo, id_torneo))
    except Exception as e:
        return jsonify({'error': f'Error al salir del torneo: {str(e)}'}), 500

    return jsonify({'mensaje': 'El equipo ha salido del torneo correctamente'}), 200





# -------------------- Main --------------------
if __name__ == '__main__':
    app.run(debug=True)
