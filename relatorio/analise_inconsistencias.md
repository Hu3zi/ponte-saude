# Relatório de análise de dados - Ponte Saúde

Gerado em 2026-10-30 16:44. Todos os dados são fictícios.

## Resumo

| Indicador | Valor |
|---|---|
| Registros no e-SUS | 39 |
| Registros no Tasy | 32 |
| Total de registros nos dois sistemas | 71 |
| Pacientes únicos após a unificação | 44 |
| Registros redundantes eliminados | 27 |
| Pacientes presentes só no e-SUS | 14 |
| Pacientes presentes só no Tasy | 8 |
| Pacientes presentes nos dois sistemas | 22 |
| Pacientes com pelo menos um alerta | 25 |
| % dos pacientes nos dois sistemas com alerta | 90.9% |
| Registros sem CPF válido (e-SUS / Tasy) | 0 / 3 |

## Inconsistências encontradas e causas prováveis

| Inconsistência | Pacientes | Causa provável |
|---|---|---|
| Alergia registrada em apenas um sistema | 9 | A alergia foi informada em um atendimento (UBS ou hospital) e não foi replicada ao outro sistema. |
| Nome escrito de formas diferentes | 6 | Abreviações, sobrenomes omitidos e uso de maiúsculas/acentos diferentes entre os sistemas. |
| Cadastro duplicado no mesmo sistema | 5 | Novo cadastro criado por não encontrar o paciente na busca (ou busca feita só por nome). |
| CPF ausente ou inválido | 3 | Campo não obrigatório na recepção; paciente atendido sem documento. |
| Medicamento em uso x alergia registrada | 2 | Cada sistema guarda a alergia e a prescrição em módulos separados; sem integração, ninguém cruza as duas informações. |
| Data de nascimento divergente | 2 | Digitação manual na entrada de dados, sem validação cruzada com outras bases. |

## Oportunidades de melhoria

- Tornar CPF/CNS obrigatório e validar os dígitos verificadores na entrada do cadastro.
- Consultar o prontuário unificado antes de criar um novo cadastro (evita duplicidades).
- Padronizar o campo de alergias (lista controlada em vez de texto livre).
- Alertar o prescritor quando um medicamento conflitar com alergia registrada em qualquer sistema.
- Adotar o padrão HL7 FHIR como formato de troca de dados entre os sistemas.

## Cenário simulado: antes e depois do Ponte Saúde

Paciente fictício: **Eduardo Moreira Martins** (PS-0008), atendido na UBS (e-SUS) e no hospital (Tasy).

- **Antes:** o médico do hospital abre o Tasy e vê alergias: nenhuma registrada; medicamentos: Dipirona. A alergia registrada na UBS (Dipirona) não aparece.
- **Depois:** o prontuário unificado do Ponte Saúde exibe o alerta crítico: Dipirona está em uso, mas o paciente tem alergia registrada a Dipirona.
