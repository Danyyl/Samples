# activities_router.py

@router.get(
    "/participants/{ppmi_id}/events/{event_id}",
    response_model=models.CalendarEventWithActivities,
    dependencies=[Depends(participants_read_scope)],
)
def get_participant_activities(
    ppmi_id: int,
    event_id: int,
    category: Optional[str] = Query(None),
    study: Optional[str] = Query(None),
    db: Session = Depends(get_session),
):
    return activity_service.get_participant_activities(
        db, ppmi_id, event_id, category, study
    )


@router.post(
    "/bulk_create",
    response_model=List[models.ActivityResponse],
    dependencies=[Depends(participants_write_scope)],
)
def bulk_create_activity(
    activities: List[models.ActivityCreate], db: Session = Depends(get_session)
):
    return activity_service.bulk_create_activity(db, activities)



# activity_service

def get_participant_activities(
    db: Session,
    ppmi_id: int,
    event_id: int,
    category: str | None = None,
    study: str | None = None,
):
    query = (
        db.query(schemas.CalendarEvent)
        .join(
            schemas.ScheduleEvent,
            schemas.CalendarEvent.schedule_event_id == schemas.ScheduleEvent.id,
        )
        .filter(schemas.CalendarEvent.id == event_id)
    )

    if category:
        query = query.filter(schemas.ScheduleEvent.category == category)

    if study:
        query = query.filter(schemas.ScheduleEvent.study == study)

    event = query.first()

    if event is None:
        raise errors.NotFoundException(
            f"Event not found for participant {ppmi_id} with event_id {event_id}"
        )

    activities = (
        db.query(schemas.Activity)
        .options(
            joinedload(schemas.Activity.activity_statuses)
        )  # Eager load activity statuses
        .filter(schemas.Activity.schedule_event_id == event.schedule_event_id)
        .all()
    )

    participant_statuses = (
        db.query(schemas.ParticipantActivityStatus)
        .filter(
            schemas.ParticipantActivityStatus.ppmi_id == ppmi_id,
            schemas.ParticipantActivityStatus.calendar_event_id == event_id,
            schemas.ParticipantActivityStatus.activity_id.in_(
                [activity.id for activity in activities]
            ),
        )
        .all()
    )

    status_lookup = {status.activity_id: status for status in participant_statuses}

    links = (
        db.query(schemas.Link)
        .filter(
            schemas.Link.id.in_(
                [
                    activity.related_entity_id
                    for activity in activities
                    if activity.type == enums.ActivityTypeEnum.link
                ]
            ),
        )
        .all()
    )

    links_lookup = {link.id: link.url for link in links}

    activity_models = []
    for activity in activities:
        activity_status = status_lookup.get(activity.id)

        activity_model = models.ActivityWithStatus(
            activity_id=activity.id,
            name=activity.name,
            description=activity.description,
            type=activity.type,
            related_entity_id=activity.related_entity_id,
            related_entity_version=(
                activity_status.related_entity_version if activity_status else None
            ),
            status=(activity_status.status if activity_status else None),
            link_url=(
                links_lookup.get(activity.related_entity_id)
                if activity.type == enums.ActivityTypeEnum.link
                else None
            ),
        )
        activity_models.append(activity_model)

    event_model = models.CalendarEventWithActivities(
        event_id=event.id,
        title=event.schedule_event.title,
        start_time=event.start_time,
        end_time=event.end_time,
        description=event.schedule_event.description,
        category=event.schedule_event.category,
        status=event.status,
        activities=activity_models,
        study=event.schedule_event.study,
        event_type=event.schedule_event.event_type,
    )

    return event_model


def bulk_create_activity(db: Session, activities: List[models.ActivityCreate]):

    type_to_ids = {}
    for activity in activities:
        type_to_ids.setdefault(activity.type, set()).add(activity.related_entity_id)

    # Query all relevant tables in a single batch query
    valid_ids = {}

    if enums.ActivityTypeEnum.survey in type_to_ids:
        valid_ids[enums.ActivityTypeEnum.survey] = {
            row[0]
            for row in db.query(schemas.Survey.id)
            .filter(schemas.Survey.id.in_(type_to_ids[enums.ActivityTypeEnum.survey]))
            .all()
        }
    if enums.ActivityTypeEnum.link in type_to_ids:
        valid_ids[enums.ActivityTypeEnum.link] = {
            row[0]
            for row in db.query(schemas.Link.id)
            .filter(schemas.Link.id.in_(type_to_ids[enums.ActivityTypeEnum.link]))
            .all()
        }

    # Validate all activities before insertion
    for activity in activities:
        if (
            activity.related_entity_id
            and activity.related_entity_id not in valid_ids.get(activity.type, set())
        ):
            raise errors.NotFoundException(
                error=f"Invalid related_entity_id {activity.related_entity_id} for type {activity.type}"
            )

    db_activities = [
        schemas.Activity(**activity.model_dump()) for activity in activities
    ]
    db.add_all(db_activities)
    db.commit()

    for activity in db_activities:
        db.refresh(activity)

    return [
        models.ActivityResponse(
            id=db_activity.id,
            name=db_activity.name,
            description=db_activity.description,
            type=db_activity.type,
            related_entity_id=db_activity.related_entity_id,
            schedule_event_id=db_activity.schedule_event_id,
        )
        for db_activity in db_activities
    ]


# database session and dependency session.py


database_urls = {
    "api": get_settings().database_url.unicode_string(),
}

engines = {
    "api": create_engine(
        database_urls["api"],
        pool_pre_ping=True,
        pool_size=20,  # Adjusted pool size for local testing
        max_overflow=30,
    ),
}


def create_session(db: str = "api") -> scoped_session:
    match db:
        case "api":
            engine = engines["api"]
        case other:
            raise Exception(f"Database {other} doesn't exist")

    session = scoped_session(sessionmaker(bind=engine, autoflush=False))
    return session


# Dependency
def get_session() -> Generator[scoped_session, None, None]:
    session = create_session("api")
    try:
        yield session
    finally:
        session.remove()


