def postponement_label(value: str | None) -> str:
    value = str(value or '').strip()
    if value in ('delay', '연기') or value.startswith('postponement.'):
        return '연기'
    if value in ('hold', '보류', '법규보류', '방침보류') or value.startswith(('statutory.', 'policy.')):
        return '보류'
    return ''
