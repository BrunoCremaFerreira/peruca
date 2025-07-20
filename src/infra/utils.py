from domain.exceptions import ValidationError


def auto_map(source_obj, target_class, raise_not_found_exception = False):
    if not source_obj:
        if raise_not_found_exception:
            raise ValidationError(errors=["Not found"], status_code=404)
        return None
    
    source_dict = vars(source_obj)
    return target_class(**{
        k: v for k, v in source_dict.items()
        if k in target_class.__init__.__code__.co_varnames
    })

def is_null_or_whitespace(s):
    return s is None or str(s).strip() == ''
