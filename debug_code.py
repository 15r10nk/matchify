class Instance:
    pass

class TupleType:
    pass

class TypedDictType:
    pass

class AnyType:
    pass

def process_item(item):
    match item:
        case Instance():
            tp = type_object_type(item.type, self.named_type)
            return self.apply_type_arguments_to_callable(tp, item.args, tapp)
        case TupleType() if item.partial_fallback.type.is_named_tuple:
            tp = type_object_type(item.partial_fallback.type, self.named_type)
            return self.apply_type_arguments_to_callable(tp, item.partial_fallback.args, tapp)
        case TypedDictType():
            return self.typeddict_callable_from_context(item)
        case _:
            self.chk.fail(message_registry.ONLY_CLASS_APPLICATION, tapp)
            return AnyType(TypeOfAny.from_error)
