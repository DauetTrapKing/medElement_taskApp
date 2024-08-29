import sqlite3
import db

# Путь к базе данных
db_path = 'C:\Users\BP\api\db.sqlite3'

# Подключение к базе данных
conn = sqlite3.connect(db)
cursor = conn.cursor()

# Выполнение запроса для получения всех имен doctor из таблицы appointments_reviews
cursor.execute("SELECT doctor FROM appointments_reviews")

# Получение всех строк результата
rows = cursor.fetchall()

# Открытие файла для записи
output_file = '/mnt/data/doctor_names.txt'
with open(output_file, 'w', encoding='utf-8') as file:
    for row in rows:
        file.write(f"{row[0]}\n")

# Закрытие соединения с базой данных
conn.close()

print(f"Data has been exported to {output_file}")
