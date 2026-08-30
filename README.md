# Tonnage

Tracker de entrenamiento y progreso físico. No gestiona un gimnasio: registra
cada entrenamiento, cada ejercicio y cada serie con mucho detalle, y enseña
tu evolución con analíticas y gráficas.

## Puesta en marcha

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # y edítalo si quieres Postgres real
python manage.py migrate
python manage.py seed_exercises
python manage.py createsuperuser
python manage.py runserver
```

Sin `DATABASE_URL` en `.env`, usa SQLite local (`db.sqlite3`) — perfecto para
desarrollar. Define `DATABASE_URL` (por ejemplo, apuntando a un proyecto de
Supabase) para usar Postgres de verdad, igual que en producción.

## Estructura

- **`accounts`** — usuario propio (`AUTH_USER_MODEL`), con preferencia de
  unidad (kg/lb), altura y fecha de nacimiento.
- **`training`** — el núcleo: catálogo de ejercicios y grupos musculares,
  rutinas (con días y ejercicios objetivo), entrenamientos reales
  (`Workout` → `WorkoutExercise` → `SetEntry`), récords personales
  (recalculados solos al guardar una serie), peso corporal y objetivos.
- **`dashboard`** — la pantalla de inicio con el resumen semanal, PRs
  recientes, racha, evolución del peso y grupos musculares trabajados.

### El modelo de datos, en una frase

Todo el peso se guarda siempre en **kg** (`weight_kg` en `SetEntry` y
`BodyWeightEntry`); `input_unit` solo recuerda en qué unidad se escribió,
para poder enseñarlo tal cual sin que comparar PRs o volumen entre entradas
en kg y en lb necesite conversión al vuelo.

Los récords personales (`PersonalRecord`) no son un histórico: son una
caché del **mejor valor actual** por `(usuario, ejercicio, tipo)` —
peso máximo, 1RM estimado, repeticiones máximas y volumen en una sesión —
que se recalcula sola cada vez que se guarda una serie (`training/prs.py`).
El histórico real ya vive en `SetEntry`/`Workout`, sin duplicar nada.

## Qué falta / próximas rondas

Esta primera pasada cubre el flujo completo (empezar entrenamiento → añadir
ejercicios → registrar series con todo el detalle pedido → PRs automáticos →
terminar → dashboard con analíticas), rutinas, catálogo de ejercicios con
gráfica de progresión de 1RM, peso corporal con gráfica, y objetivos.
Quedan como mejoras naturales para siguientes rondas: edición inline de
series ya registradas desde la propia tabla (hoy se borran y se vuelven a
añadir), soporte HTMX para que añadir series no recargue la página, y
exportar/compartir un entrenamiento o una gráfica como imagen.
