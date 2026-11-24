from __future__ import annotations

import pytest

from distroforge.labels import iso_volume_label


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Minha Distro", "MINHA_DISTRO"),
        ("Minha Distro 1.0", "MINHA_DISTRO_1_0"),
        ("a-b c", "A_B_C"),
        ("  ", "DISTROFORGE"),
        ("acentuação", "ACENTUA_O"),
    ],
)
def test_rotulo_valido(text, expected):
    label = iso_volume_label(text)
    assert label == expected
    assert 0 < len(label) <= 32
    assert all(ch.isalnum() or ch == "_" for ch in label)


def test_respeita_tamanho_maximo():
    assert len(iso_volume_label("x" * 100, max_len=11)) == 11
