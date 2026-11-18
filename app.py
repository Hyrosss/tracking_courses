"""Dashboard de révisions Streamlit avec PostgreSQL / Supabase.

Table existante : course(id, course_name, total_courses, revised_courses)
"""

import streamlit as st
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError


st.set_page_config(
    page_title="Suivi des révisions",
    page_icon="📚",
    layout="centered",
)

conn = st.connection("db", type="sql")


def charger_cours():
    """Recharge les données à chaque exécution, sans cache persistant."""
    return conn.query(
        "SELECT id, course_name, total_courses, revised_courses "
        "FROM course ORDER BY id",
        ttl=0,
    )


def executer_modification(requete, params):
    """Exécute une écriture SQL puis la valide dans Supabase."""
    try:
        with conn.session as session:
            resultat = session.execute(text(requete), params)
            session.commit()
            return resultat.rowcount
    except SQLAlchemyError:
        st.error("La modification a échoué. Vérifie la connexion et les droits Supabase.")
        return 0


def actualiser(message=None):
    if message:
        st.session_state["notification"] = message
    st.rerun()


def modifier_revision(id_cours, delta):
    return executer_modification(
        """
        UPDATE course
        SET revised_courses = revised_courses + :delta
        WHERE id = :id
          AND revised_courses + :delta BETWEEN 0 AND total_courses
        """,
        {"id": id_cours, "delta": delta},
    )


def page_progression():
    st.title("📚 Mes révisions")
    st.caption("Suivez vos cours révisés, matière par matière.")

    df = charger_cours()
    if df.empty:
        st.info("Aucune matière pour l'instant. Ajoute-en une dans Configuration.")
        return

    total_revus = int(df["revised_courses"].sum())
    total_cours = int(df["total_courses"].sum())
    progression = total_revus / total_cours if total_cours else 0.0

    col1, col2, col3 = st.columns(3)
    col1.metric("Cours révisés", total_revus)
    col2.metric("Total des cours", total_cours)
    col3.metric("Progression", f"{progression:.0%}")

    st.progress(min(max(progression, 0.0), 1.0))
    st.divider()
    st.subheader("Progression par matière")

    for cours in df.itertuples(index=False):
        id_cours = int(cours.id)
        revus = int(cours.revised_courses)
        total = int(cours.total_courses)
        taux = revus / total if total else 0.0

        with st.container(border=True):
            titre, compte = st.columns([3, 1], vertical_alignment="center")
            with titre:
                st.markdown(f"**{cours.course_name}**")
            with compte:
                st.caption(f"{revus} / {total} cours")

            st.progress(min(max(taux, 0.0), 1.0))
            st.caption(f"{taux:.0%} des cours révisés")

            plus, moins, _ = st.columns([1, 1, 2])
            with plus:
                if st.button(
                    "➕",
                    key=f"plus_{id_cours}",
                    disabled=revus >= total,
                    use_container_width=True,
                ):
                    if modifier_revision(id_cours, 1):
                        actualiser()
            with moins:
                if st.button(
                    "➖",
                    key=f"moins_{id_cours}",
                    disabled=revus <= 0,
                    use_container_width=True,
                ):
                    if modifier_revision(id_cours, -1):
                        actualiser()


def page_configuration():
    st.title("⚙️ Configuration")
    st.caption("Ajoutez vos matières et gérez le nombre total de cours.")

    with st.container(border=True):
        st.subheader("Ajouter une matière")
        with st.form("ajout_matiere", clear_on_submit=True):
            nouveau_nom = st.text_input("Nom de la matière", placeholder="Ex. : Machine Learning")
            total_initial = st.number_input("Nombre total de cours", min_value=0, value=10, step=1)
            revus_initial = st.number_input("Cours déjà révisés", min_value=0, value=0, step=1)
            ajouter = st.form_submit_button("Ajouter la matière", type="primary")

        if ajouter:
            nom = nouveau_nom.strip()
            if not nom:
                st.warning("Saisis un nom de matière.")
            elif revus_initial > total_initial:
                st.warning("Le nombre de cours révisés ne peut pas dépasser le total.")
            else:
                doublon = conn.query(
                    "SELECT id FROM course WHERE LOWER(course_name) = LOWER(:nom)",
                    params={"nom": nom},
                    ttl=0,
                )
                if not doublon.empty:
                    st.warning("Cette matière existe déjà.")
                elif executer_modification(
                    """
                    INSERT INTO course (course_name, total_courses, revised_courses)
                    VALUES (:nom, :total, :revus)
                    """,
                    {"nom": nom, "total": int(total_initial), "revus": int(revus_initial)},
                ):
                    actualiser("Matière ajoutée avec succès.")

    st.divider()
    st.subheader("Gérer les matières")
    df = charger_cours()

    if df.empty:
        st.info("Aucune matière à modifier.")
        return

    for cours in df.itertuples(index=False):
        id_cours = int(cours.id)
        revus = int(cours.revised_courses)
        total = int(cours.total_courses)

        with st.expander(f"{cours.course_name}  ·  {revus}/{total} révisés"):
            with st.form(f"edition_{id_cours}"):
                nom_modifie = st.text_input(
                    "Nom de la matière",
                    value=cours.course_name,
                    key=f"nom_{id_cours}",
                )
                total_modifie = st.number_input(
                    "Nombre total de cours",
                    min_value=revus,
                    value=total,
                    step=1,
                    key=f"total_{id_cours}",
                )
                enregistrer = st.form_submit_button("Enregistrer les modifications")

            if enregistrer:
                nom = nom_modifie.strip()
                if not nom:
                    st.warning("Le nom de la matière ne peut pas être vide.")
                else:
                    doublon = conn.query(
                        """
                        SELECT id FROM course
                        WHERE LOWER(course_name) = LOWER(:nom) AND id <> :id
                        """,
                        params={"nom": nom, "id": id_cours},
                        ttl=0,
                    )
                    if not doublon.empty:
                        st.warning("Une autre matière porte déjà ce nom.")
                    elif executer_modification(
                        """
                        UPDATE course
                        SET course_name = :nom, total_courses = :total
                        WHERE id = :id AND :total >= revised_courses
                        """,
                        {"nom": nom, "total": int(total_modifie), "id": id_cours},
                    ):
                        actualiser("Matière mise à jour.")
                    else:
                        st.warning("Modification non effectuée. Actualise la page.")

            st.divider()
            confirmer = st.checkbox(
                "Je confirme vouloir supprimer définitivement cette matière",
                key=f"confirm_{id_cours}",
            )
            if st.button(
                "🗑️ Supprimer la matière",
                key=f"delete_{id_cours}",
                disabled=not confirmer,
            ):
                if executer_modification(
                    "DELETE FROM course WHERE id = :id",
                    {"id": id_cours},
                ):
                    actualiser("Matière supprimée.")


page_progression_ref = st.Page(
    page_progression,
    title="Progression",
    icon="📊",
    default=True,
)
page_configuration_ref = st.Page(
    page_configuration,
    title="Configuration",
    icon="⚙️",
)

with st.sidebar:
    st.title("📚 Révisions")
    st.caption("Données enregistrées dans Supabase")

page = st.navigation([page_progression_ref, page_configuration_ref], position="sidebar")

if "notification" in st.session_state:
    st.success(st.session_state.pop("notification"))

page.run()
