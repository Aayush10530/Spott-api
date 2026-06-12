from rest_framework import serializers


class TripRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        max_length=200,
        help_text="Starting US location, e.g. 'New York, NY'"
    )
    finish = serializers.CharField(
        max_length=200,
        help_text="Destination US location, e.g. 'Los Angeles, CA'"
    )

    def validate_start(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Start location cannot be blank.")
        return value

    def validate_finish(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Finish location cannot be blank.")
        return value

    def validate(self, data: dict) -> dict:
        if data.get('start', '').lower() == data.get('finish', '').lower():
            raise serializers.ValidationError(
                "Start and finish locations must be different."
            )
        return data
