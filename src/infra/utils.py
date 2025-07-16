def auto_map(source_obj, target_class):
    source_dict = vars(source_obj)
    return target_class(**{
        k: v for k, v in source_dict.items()
        if k in target_class.__init__.__code__.co_varnames
    })