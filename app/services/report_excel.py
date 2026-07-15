"""Формирование Excel-отчётов 7.1 и 7.2 по ТЗ."""



from __future__ import annotations



import re

from uuid import UUID



from openpyxl import Workbook

from openpyxl.styles import Alignment

from openpyxl.utils import get_column_letter

from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload



from app.models import PlanDiscipline, Profile, StudyPlan

from app.models_tz import AuthorLoad

from app.services.department_lookup import department_names_by_codes

from app.services.report_scoring import UniquePointsTracker, points_for_author, split_author_loads

from app.services.rpd_extractor import RpdExtract, authors_to_cell





def _format_direction_cell(direction_code: str, direction_name: str, profile_name: str) -> str:

    base = f'направление {direction_code} "{direction_name}"'

    if profile_name:

        return f"{base} {profile_name}"

    return base





def _wrap_alignment() -> Alignment:

    return Alignment(wrap_text=True, vertical="top")





def _autosize_columns(ws, max_width: int = 48) -> None:

    for col_idx, column_cells in enumerate(ws.columns, start=1):

        length = 0

        for cell in column_cells:

            if cell.value:

                for line in str(cell.value).split("\n"):

                    length = max(length, len(line))

        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(length + 2, 10), max_width)





def _authors_from_program(program) -> list[str]:

    if program is None or not program.rpd_extract_json:

        return []

    rpd = RpdExtract.from_json(program.rpd_extract_json)

    return rpd.authors if rpd else []





def _sheet_ref(name: str) -> str:

    escaped = name.replace("'", "''")

    if re.search(r"[\s'!\-\[\]]", name):

        return f"'{escaped}'"

    return escaped





def _author_marker(name: str) -> str:

    return f"*{name}*"





def _dept_code_value(code: str | None) -> int | str | None:

    if not code:

        return None

    try:

        return int(str(code).strip())

    except ValueError:

        return code





async def build_plan_summary_workbook(db: AsyncSession, plan_id: UUID) -> Workbook:

    """Отчёт 7.1 — свод по учебному плану (8 колонок по эталону)."""

    plan = await db.get(StudyPlan, plan_id)

    if plan is None:

        raise ValueError("Учебный план не найден")



    profile = await db.get(Profile, plan.profile_id, options=[selectinload(Profile.direction)])

    direction = profile.direction if profile else None



    result = await db.execute(

        select(PlanDiscipline)

        .options(selectinload(PlanDiscipline.program))

        .where(PlanDiscipline.study_plan_id == plan_id)

        .order_by(PlanDiscipline.row_order)

    )

    disciplines = list(result.scalars().all())



    dept_codes = {d.department_code for d in disciplines if d.department_code}

    dept_names = await department_names_by_codes(db, dept_codes, enrollment_year=plan.year)



    wb = Workbook()

    ws = wb.active

    ws.title = "Лист1"

    headers = [

        "Учебный план",

        "Направление подготовки",

        "Код кафедры",

        "Название кафедры",

        "Шифр дисциплины",

        "Наименование дисциплины",

        "Объем дисциплины в з.е.",

        "Автор",

    ]

    ws.append(headers)



    direction_code = direction.code if direction else ""

    direction_name = direction.name if direction else ""

    profile_name = profile.name if profile else ""

    direction_cell = _format_direction_cell(direction_code, direction_name, profile_name)



    for discipline in disciplines:

        program = discipline.program

        dept_code = discipline.department_code or ""

        ws.append(

            [

                plan.source_file,

                direction_cell,

                dept_code,

                dept_names.get(dept_code, ""),

                discipline.code,

                discipline.name,

                discipline.credits if discipline.credits is not None else "",

                authors_to_cell(_authors_from_program(program)),

            ]

        )



    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):

        for cell in row:

            cell.alignment = _wrap_alignment()



    _autosize_columns(ws)

    return wb





async def build_author_rating_workbook(db: AsyncSession, plan_id: UUID) -> Workbook:

    """Отчёт 7.2 — структура эталона Otchet_po_razrabotke_RPd_2025_1.xlsx."""

    plan = await db.get(StudyPlan, plan_id)

    if plan is None:

        raise ValueError("Учебный план не найден")



    result = await db.execute(

        select(PlanDiscipline)

        .options(selectinload(PlanDiscipline.program))

        .where(PlanDiscipline.study_plan_id == plan_id)

        .order_by(PlanDiscipline.row_order)

    )

    disciplines = list(result.scalars().all())



    loads_result = await db.execute(

        select(AuthorLoad).where(

            AuthorLoad.plan_discipline_id.in_([d.id for d in disciplines])

        )

    )

    loads_by_disc: dict[UUID, list[AuthorLoad]] = {}

    for load in loads_result.scalars().all():

        loads_by_disc.setdefault(load.plan_discipline_id, []).append(load)



    dept_codes = {d.department_code for d in disciplines if d.department_code}

    dept_names = await department_names_by_codes(db, dept_codes, enrollment_year=plan.year)



    detail_headers = [

        "Дисциплина",

        "Шифр",

        "Учебный план",

        "Преподаватель",

        "з.е.",

        "Количество баллов за 1 з.е.",

        "Сумма баллов",

        "Количество авторов",

        "Количество баллов ",

        "Количество баллов без повторов",

    ]



    rows_by_author: dict[str, list[dict]] = {}

    summary_rows: dict[str, dict] = {}

    unique_tracker = UniquePointsTracker()

    author_dept_codes: dict[str, str | None] = {}



    for discipline in disciplines:

        credits = float(discipline.credits or 0)

        program = discipline.program

        loads = loads_by_disc.get(discipline.id) or []

        rpd_authors = _authors_from_program(program)

        splits = split_author_loads(loads, rpd_authors)



        author_names = [name for name, _load, _share in splits]

        teacher_cell = "\n".join(author_names) if author_names else "—"



        if splits:

            points_per = float(

                splits[0][1].points_per_credit if splits[0][1] and splits[0][1].points_per_credit else 20

            )

            total = round(sum(points_for_author(credits, load, share)[1] for _n, load, share in splits), 2)

            author_count = len(splits)

        else:

            points_per = 20.0

            total = round(credits * points_per, 2)

            author_count = 1



        summary_rows[discipline.code] = {

            "name": discipline.name,

            "code": discipline.code,

            "plan_file": plan.source_file,

            "teacher_cell": teacher_cell,

            "credits": credits,

            "points_per": points_per,

            "total": total,

        }



        targets = splits or [(author_names[0] if author_names else "—", None, 100.0)]

        coauthor_cell = teacher_cell if len(targets) > 1 else None

        for author_name, load, share in targets:

            if author_name == "—":

                continue

            pts_per, author_total = points_for_author(credits, load, share)

            per_author = round(author_total, 2)

            unique_points = unique_tracker.unique_for(author_name, discipline.code, per_author)

            if discipline.department_code and author_name not in author_dept_codes:

                author_dept_codes[author_name] = discipline.department_code

            rows_by_author.setdefault(author_name, []).append(

                {

                    "name": discipline.name,

                    "code": discipline.code,

                    "plan_file": plan.source_file,

                    "teacher_cell": coauthor_cell or author_name,

                    "credits": credits,

                    "points_per": pts_per,

                    "author_count": author_count,

                    "unique_points": unique_points,

                }

            )



    wb = Workbook()

    wb.remove(wb.active)



    ws_ref = wb.create_sheet("Справочник", 0)

    ws_ref.append(["Номер", "Название кафедры"])

    for code in sorted(dept_names, key=lambda item: str(item)):

        ws_ref.append([_dept_code_value(code), dept_names[code]])



    ws_summary = wb.create_sheet("Свод", 3)

    svod_header_row = 6

    svod_data_start = 7

    ws_summary.cell(svod_header_row, 1, "Дисциплина")

    ws_summary.cell(svod_header_row, 2, "Шифр")

    ws_summary.cell(svod_header_row, 3, "Учебный план")

    ws_summary.cell(svod_header_row, 4, "Преподаватель")

    ws_summary.cell(svod_header_row, 5, "з.е.")

    ws_summary.cell(svod_header_row, 6, "Баллы ")

    ws_summary.cell(svod_header_row, 7, "Балл за РП")



    svod_row = svod_data_start

    for discipline in disciplines:

        row_data = summary_rows.get(discipline.code)

        if not row_data:

            continue

        ws_summary.cell(svod_row, 1, row_data["name"])

        ws_summary.cell(svod_row, 2, row_data["code"])

        ws_summary.cell(svod_row, 3, row_data["plan_file"])

        ws_summary.cell(svod_row, 4, row_data["teacher_cell"])

        ws_summary.cell(svod_row, 5, row_data["credits"])

        ws_summary.cell(

            svod_row,

            6,

            f"=E{svod_row}*{int(row_data['points_per']) if row_data['points_per'] == int(row_data['points_per']) else row_data['points_per']}",

        )

        ws_summary.cell(svod_row, 7, row_data["total"])

        for col in range(1, 8):

            ws_summary.cell(svod_row, col).alignment = _wrap_alignment()

        svod_row += 1

    svod_last_row = max(svod_row - 1, svod_data_start)



    author_sheet_names: dict[str, str] = {}

    for author in sorted(rows_by_author):

        sheet_name = author[:31]

        author_sheet_names[author] = sheet_name

        ws = wb.create_sheet(sheet_name)

        dept_code = author_dept_codes.get(author)

        dept_name = dept_names.get(dept_code or "", "") if dept_code else ""



        ws.cell(1, 1, "Ф.И.О.:")

        ws.cell(1, 2, author)

        if dept_code:

            ws.cell(1, 9, _dept_code_value(dept_code))

        ws.cell(2, 1, "Кафедра:")

        ws.cell(2, 2, dept_name)

        ws.cell(3, 1, "Итого")



        for col_idx, header in enumerate(detail_headers, start=1):

            ws.cell(4, col_idx, header)



        detail_start = 5

        row_idx = detail_start

        for row in rows_by_author[author]:

            ws.cell(row_idx, 1, row["name"])

            ws.cell(row_idx, 2, row["code"])

            ws.cell(row_idx, 3, row["plan_file"])

            ws.cell(row_idx, 4, row["teacher_cell"])

            ws.cell(row_idx, 5, row["credits"])

            ws.cell(row_idx, 6, row["points_per"])

            ws.cell(row_idx, 7, f"=E{row_idx}*F{row_idx}")

            ws.cell(row_idx, 8, row["author_count"])

            ws.cell(row_idx, 9, f"=G{row_idx}/H{row_idx}")

            ws.cell(row_idx, 10, f"=I{row_idx}")

            for col in range(1, 11):

                ws.cell(row_idx, col).alignment = _wrap_alignment()

            row_idx += 1

        detail_last = max(row_idx - 1, detail_start)

        ws.cell(3, 2, f"=SUM(J{detail_start}:J{detail_last})")



    ws_teachers = wb.create_sheet("Преподаватели", 1)

    teacher_headers = [

        "№",

        None,

        "Ф.И.О.",

        "Свод",

        "Вкладка",

        "Индикатор",

        "Каф",

        "Балл из свод",

        "Баллы",

        "Индикатор",

    ]

    ws_teachers.append(teacher_headers)



    authors_sorted = sorted(rows_by_author)

    for idx, author in enumerate(authors_sorted, start=1):

        row_num = idx + 1

        sheet_name = author_sheet_names[author]

        sheet_ref = _sheet_ref(sheet_name)

        marker = _author_marker(author)

        dept_code = author_dept_codes.get(author)



        ws_teachers.cell(row_num, 1, idx)

        ws_teachers.cell(row_num, 2, marker)

        ws_teachers.cell(row_num, 3, author)

        ws_teachers.cell(row_num, 4, f"=COUNTIF(Свод!D${svod_header_row}:D${svod_last_row + 200},B{row_num})")

        ws_teachers.cell(row_num, 5, f"=COUNTIF({sheet_ref}!D$5:D$200,B{row_num})")

        ws_teachers.cell(row_num, 6, f"=IF(D{row_num}=E{row_num},1,0)")

        if dept_code is not None:

            ws_teachers.cell(row_num, 7, _dept_code_value(dept_code))

        ws_teachers.cell(

            row_num,

            8,

            f"=SUMIF(Свод!$D${svod_data_start}:$D${svod_last_row + 200},Преподаватели!B{row_num},Свод!$F${svod_data_start}:$F${svod_last_row + 200})",

        )

        ws_teachers.cell(row_num, 9, f"={sheet_ref}!B3")

        ws_teachers.cell(row_num, 10, f"=IF(H{row_num}=I{row_num},1,0)")



    ws_totals = wb.create_sheet("Сводная баллов", 2)

    ws_totals.cell(1, 1, "№")

    ws_totals.cell(1, 3, "Ф.И.О.")

    ws_totals.cell(1, 4, "Баллы")

    ws_totals.cell(1, 7, "Всего баллов ")



    for idx, author in enumerate(authors_sorted, start=1):

        row_num = idx + 1

        ws_totals.cell(row_num, 1, idx)

        ws_totals.cell(row_num, 2, _author_marker(author))

        ws_totals.cell(row_num, 3, author)

        ws_totals.cell(row_num, 4, f"=Преподаватели!I{row_num}")



    if authors_sorted:

        ws_totals.cell(2, 7, f"=SUM(D2:D{len(authors_sorted) + 1})")



    for sheet in (ws_ref, ws_teachers, ws_totals, ws_summary):

        _autosize_columns(sheet, max_width=40)



    return wb

