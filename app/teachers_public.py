# Порядок карточек на главной
PUBLIC_TEACHER_SLUGS = (
    'chin-sofya',
    'andreeva-ekaterina',
    'korotkov-ilya',
)


PUBLIC_TEACHERS = {
    'chin-sofya': {
        'slug': 'chin-sofya',
        'full_name': 'Чин Софья Дмитриевна',
        'tagline': 'Педагог-психолог, учитель иностранного языка (китайский)',
        'email': 'teacher.chin@example.com',
        'qualifications': (
            'Здесь укажите образование, стаж, сертификаты и достижения преподавателя.'
        ),
        'photo_url': (
            'https://images.unsplash.com/photo-1574169208507-84376144848b'
            '?ixlib=rb-4.0.3&w=800'
        ),
    },
    'andreeva-ekaterina': {
        'slug': 'andreeva-ekaterina',
        'full_name': 'Андреева Екатерина Андреевна',
        'tagline': 'Учитель иностранного языка (китайский, английский)',
        'email': 'teacher.andreeva@example.com',
        'qualifications': (
            'Здесь укажите образование, стаж, сертификаты и достижения преподавателя.'
        ),
        'photo_url': (
            'https://images.unsplash.com/photo-1563089145-599997674d42'
            '?ixlib=rb-4.0.3&w=800'
        ),
    },
    'korotkov-ilya': {
        'slug': 'korotkov-ilya',
        'full_name': 'Коротков Илья Александрович',
        'tagline': 'Учитель физики, информатики, математики',
        'email': 'teacher.korotkov@example.com',
        'qualifications': (
            'Здесь укажите образование, стаж, сертификаты и достижения преподавателя.'
        ),
        'photo_url': (
            'https://images.unsplash.com/photo-1557672172-298e090bd0f1'
            '?ixlib=rb-4.0.3&w=800'
        ),
    },
}


def public_teachers_list():
    return [PUBLIC_TEACHERS[slug] for slug in PUBLIC_TEACHER_SLUGS]
